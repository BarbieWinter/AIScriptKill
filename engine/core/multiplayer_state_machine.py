"""Pure, synchronous reducer for the Multiplayer v1 offline stage flow."""

from collections import Counter
from collections.abc import Iterable
from typing import TypeAlias

from engine.contracts.multiplayer_v1.authoring import (
    FinalJudgmentSettlementDefinition,
    MultiplayerStageDefinition,
    NoSettlementDefinition,
    SecretVoteSettlementDefinition,
    SettlementOption,
    SharedChoiceSettlementDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    ConfirmDiscussionCloseCommand,
    ConfirmReadCommand,
    ConfirmSharedChoiceCommand,
    HintConfirmCommand,
    HintRequestCommand,
    RevokeDiscussionCloseCommand,
    SubmitSettlementCommand,
)
from engine.contracts.multiplayer_v1.state import (
    GameStateV2,
    HintRuntimeState,
    PrivatePlayerState,
    PrivateSettlementSubmission,
    RevealedBallot,
    RevealedOptionCount,
    SettlementRuntimeState,
    StageRuntimeState,
)
from engine.contracts.multiplayer_v1.vocabulary import (
    FinalAnswerMode,
    RoomStatus,
    SettlementEffect,
    SettlementReveal,
    StagePhase,
    SubmissionChangePolicy,
)

StageMutationCommand: TypeAlias = (
    ConfirmReadCommand
    | ConfirmDiscussionCloseCommand
    | RevokeDiscussionCloseCommand
    | SubmitSettlementCommand
    | ConfirmSharedChoiceCommand
    | HintRequestCommand
    | HintConfirmCommand
)


class InvalidStageTransitionError(ValueError):
    """Raised when a command does not apply to the authoritative stage state."""


def initialize_stage_runtime(
    definition: MultiplayerStageDefinition,
    *,
    required_member_ids: tuple[str, ...],
) -> StageRuntimeState:
    """Construct canonical READ state for a stage definition and locked room members."""

    if not required_member_ids or len(required_member_ids) != len(set(required_member_ids)):
        raise InvalidStageTransitionError("required_member_ids must be non-empty and unique")

    settlement_definition = definition.settlement
    settlement = None
    if not isinstance(settlement_definition, NoSettlementDefinition):
        settlement = SettlementRuntimeState(
            settlement_id=settlement_definition.settlement_id,
            mode=settlement_definition.mode,
            required_member_ids=required_member_ids,
        )

    return StageRuntimeState(
        stage_id=definition.id,
        phase=StagePhase.READ,
        settlement=settlement,
        revealed_material_ids=_material_ids_for_triggers(definition, {"stage_enter"}),
        hints=tuple(HintRuntimeState(hint_id=hint.id) for hint in definition.hints),
    )


def reduce_stage_command(
    state: GameStateV2,
    command: StageMutationCommand,
    *,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    """Apply one authenticated stage command without mutating input or changing revision."""

    _validate_stage_context(state, actor_member_id=actor_member_id, definition=definition)

    if isinstance(command, ConfirmReadCommand):
        _validate_stage_id(state, command.payload.stage_id)
        return _confirm_read(
            state,
            actor_member_id,
            definition=definition,
        )
    if isinstance(command, ConfirmDiscussionCloseCommand):
        _validate_stage_id(state, command.payload.stage_id)
        return _change_discussion_confirmation(
            state,
            actor_member_id,
            confirmed=True,
            definition=definition,
        )
    if isinstance(command, RevokeDiscussionCloseCommand):
        _validate_stage_id(state, command.payload.stage_id)
        return _change_discussion_confirmation(
            state,
            actor_member_id,
            confirmed=False,
            definition=definition,
        )
    if isinstance(command, SubmitSettlementCommand):
        return _submit_secret_settlement(state, command, actor_member_id, definition)
    if isinstance(command, ConfirmSharedChoiceCommand):
        return _confirm_shared_choice(state, command, actor_member_id, definition)
    if isinstance(command, HintRequestCommand):
        return _request_hint(state, command, actor_member_id, definition)
    return _confirm_hint(state, command, actor_member_id, definition)


def complete_final_judgment(
    state: GameStateV2,
    *,
    definition: MultiplayerStageDefinition,
    ending_ids: Iterable[str],
) -> GameStateV2:
    """Complete a revealed final judgment by selecting the same-ID authored ending."""

    _validate_definition_matches_state(state, definition)
    if state.room.status is not RoomStatus.ACTIVE:
        raise InvalidStageTransitionError("completion requires an active room")
    settlement_definition = definition.settlement
    if not isinstance(settlement_definition, FinalJudgmentSettlementDefinition):
        raise InvalidStageTransitionError("completion requires a final judgment settlement")
    if settlement_definition.default_effect is not SettlementEffect.BRANCH:
        raise InvalidStageTransitionError("final judgment must declare branch completion")
    if state.stage.phase is not StagePhase.REVEAL:
        raise InvalidStageTransitionError("the final judgment must be in reveal phase")

    settlement = state.stage.settlement
    if settlement is None or (
        not settlement.revealed
        or settlement.outcome_id is None
        or settlement.submitted_member_ids != state.room.required_member_ids
    ):
        raise InvalidStageTransitionError(
            "the final judgment must be completed and revealed before room completion"
        )

    available_endings = frozenset(ending_ids)
    if settlement.outcome_id not in available_endings:
        raise InvalidStageTransitionError(
            "the final judgment outcome does not map to an authored ending"
        )

    completed = state.model_copy(
        update={
            "room": state.room.model_copy(update={"status": RoomStatus.COMPLETED}),
            "ending_id": settlement.outcome_id,
        }
    )
    return GameStateV2.model_validate(completed.model_dump())


def enter_next_stage(
    state: GameStateV2,
    *,
    current_definition: MultiplayerStageDefinition,
    next_definition: MultiplayerStageDefinition,
) -> GameStateV2:
    """Perform the trusted, synchronous transition after an observable REVEAL phase."""

    _validate_definition_matches_state(state, current_definition)
    if state.room.status is not RoomStatus.ACTIVE:
        raise InvalidStageTransitionError("stage entry requires an active room")
    if state.stage.phase is not StagePhase.REVEAL:
        raise InvalidStageTransitionError("the current stage must be in reveal phase")
    settlement = state.stage.settlement
    if settlement is not None and (
        not settlement.revealed
        or settlement.outcome_id is None
        or settlement.submitted_member_ids != state.room.required_member_ids
    ):
        raise InvalidStageTransitionError(
            "the active settlement must be completed and revealed before stage entry"
        )
    if current_definition.settlement.default_effect is not SettlementEffect.RECORD_AND_CONTINUE:
        raise InvalidStageTransitionError("branch settlement resolution is not implemented")

    private_by_member: dict[str, PrivatePlayerState] = {}
    for member_id in state.room.required_member_ids:
        player = state.players[member_id]
        if player.character_id is None:
            raise InvalidStageTransitionError(
                "every required member must have an assigned character"
            )
        try:
            chapter_id = next_definition.chapters[player.character_id]
        except KeyError as exc:
            raise InvalidStageTransitionError(
                f"next stage has no chapter for character {player.character_id!r}"
            ) from exc
        private_state = state.private_by_member[member_id]
        unlocked = private_state.unlocked_chapter_ids
        if chapter_id not in unlocked:
            unlocked = (*unlocked, chapter_id)
        private_by_member[member_id] = private_state.model_copy(
            update={
                "unlocked_chapter_ids": unlocked,
                "settlement_submission": None,
            }
        )

    next_stage = initialize_stage_runtime(
        next_definition,
        required_member_ids=state.room.required_member_ids,
    )
    next_room = state.room.model_copy(update={"current_stage_id": next_definition.id})
    next_state = state.model_copy(
        update={
            "room": next_room,
            "private_by_member": private_by_member,
            "stage": next_stage,
        }
    )
    return GameStateV2.model_validate(next_state.model_dump())


def _validate_stage_context(
    state: GameStateV2,
    *,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> None:
    if state.room.status is not RoomStatus.ACTIVE:
        raise InvalidStageTransitionError("stage commands require an active room")
    if actor_member_id not in state.room.required_member_ids:
        raise InvalidStageTransitionError("actor must be a locked required room member")
    _validate_definition_matches_state(state, definition)


def _validate_definition_matches_state(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
) -> None:
    if definition.id != state.stage.stage_id or state.room.current_stage_id != definition.id:
        raise InvalidStageTransitionError("stage definition does not match the current stage")

    settlement_definition = definition.settlement
    settlement = state.stage.settlement
    if isinstance(settlement_definition, NoSettlementDefinition):
        if settlement is not None:
            raise InvalidStageTransitionError(
                "no-settlement stage has unexpected runtime settlement"
            )
    elif (
        settlement is None
        or settlement.settlement_id != settlement_definition.settlement_id
        or settlement.mode is not settlement_definition.mode
    ):
        raise InvalidStageTransitionError("settlement runtime does not match stage definition")

    authored_hint_ids = tuple(hint.id for hint in definition.hints)
    runtime_hint_ids = tuple(hint.hint_id for hint in state.stage.hints)
    if runtime_hint_ids != authored_hint_ids:
        raise InvalidStageTransitionError("hint runtime does not match stage definition")


def _validate_stage_id(state: GameStateV2, stage_id: str) -> None:
    if stage_id != state.stage.stage_id:
        raise InvalidStageTransitionError("command stage_id does not match the current stage")


def _canonical_members(state: GameStateV2, members: Iterable[str]) -> tuple[str, ...]:
    member_set = set(members)
    return tuple(
        member_id for member_id in state.room.required_member_ids if member_id in member_set
    )


def _confirm_read(
    state: GameStateV2,
    actor_member_id: str,
    *,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    if state.stage.phase is not StagePhase.READ:
        raise InvalidStageTransitionError("read confirmation is allowed only during read phase")

    members = set(state.stage.read_member_ids)
    members.add(actor_member_id)
    read_member_ids = _canonical_members(state, members)

    stage_updates: dict[str, object] = {"read_member_ids": read_member_ids}
    if read_member_ids == state.room.required_member_ids:
        stage_updates.update(
            phase=StagePhase.DISCUSS,
            revealed_material_ids=_material_ids_for_triggers(
                definition,
                {"stage_enter", "all_players_read"},
            ),
        )
    return _copy_with_stage_updates(state, **stage_updates)


def _change_discussion_confirmation(
    state: GameStateV2,
    actor_member_id: str,
    *,
    confirmed: bool,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    if state.stage.phase is not StagePhase.DISCUSS:
        raise InvalidStageTransitionError(
            "discussion close confirmation can change only during discuss phase"
        )

    members = set(state.stage.discussion_close_member_ids)
    if confirmed:
        members.add(actor_member_id)
    else:
        members.discard(actor_member_id)
    close_member_ids = _canonical_members(state, members)

    stage_updates: dict[str, object] = {"discussion_close_member_ids": close_member_ids}
    if close_member_ids == state.room.required_member_ids:
        if isinstance(definition.settlement, NoSettlementDefinition):
            stage_updates.update(
                phase=StagePhase.REVEAL,
                revealed_material_ids=_material_ids_for_triggers(
                    definition,
                    {"stage_enter", "all_players_read", "settlement_done"},
                ),
            )
        else:
            stage_updates["phase"] = StagePhase.SETTLE
    return _copy_with_stage_updates(state, **stage_updates)


def _submit_secret_settlement(
    state: GameStateV2,
    command: SubmitSettlementCommand,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    settlement_definition = definition.settlement
    if isinstance(settlement_definition, SecretVoteSettlementDefinition):
        pass
    elif isinstance(settlement_definition, FinalJudgmentSettlementDefinition):
        if settlement_definition.answer_mode is not FinalAnswerMode.INDIVIDUAL_SECRET:
            raise InvalidStageTransitionError(
                "final judgment is not an individual secret settlement"
            )
    else:
        raise InvalidStageTransitionError(
            "settlement.submit requires an individual secret settlement"
        )

    settlement = _require_settlement(state, command.payload.settlement_id)
    if state.stage.phase is not StagePhase.SETTLE:
        raise InvalidStageTransitionError("secret submission requires settle phase")
    option = _find_option(settlement_definition.options, command.payload.option_id)

    actor_private = state.private_by_member[actor_member_id]
    previous = actor_private.settlement_submission
    if previous is not None and previous.settlement_id == settlement.settlement_id:
        if settlement_definition.submission_change is SubmissionChangePolicy.FORBIDDEN:
            raise InvalidStageTransitionError("settlement submission cannot be changed")

    private_by_member = {
        member_id: state.private_by_member[member_id]
        for member_id in state.room.required_member_ids
    }
    private_by_member[actor_member_id] = actor_private.model_copy(
        update={
            "settlement_submission": PrivateSettlementSubmission(
                settlement_id=settlement.settlement_id,
                option_id=option.id,
            )
        }
    )
    submitted_member_ids = _canonical_members(
        state,
        (*settlement.submitted_member_ids, actor_member_id),
    )
    next_settlement = settlement.model_copy(update={"submitted_member_ids": submitted_member_ids})

    if submitted_member_ids != state.room.required_member_ids:
        return _copy_state(
            state,
            private_by_member=private_by_member,
            stage=state.stage.model_copy(update={"settlement": next_settlement}),
        )

    submissions = tuple(
        _require_private_submission(
            private_by_member[member_id],
            settlement_id=settlement.settlement_id,
        )
        for member_id in state.room.required_member_ids
    )
    counts = Counter(submission.option_id for submission in submissions)
    highest_count = max(counts.values())
    highest_option_ids = tuple(
        option_id for option_id, count in counts.items() if count == highest_count
    )
    if len(highest_option_ids) == 1:
        outcome_id = _option_outcome_id(
            _find_option(settlement_definition.options, highest_option_ids[0])
        )
    else:
        outcome_id = _tie_outcome_id(settlement_definition)

    ballots: tuple[RevealedBallot, ...] = ()
    option_counts: tuple[RevealedOptionCount, ...] = ()
    if settlement_definition.reveal is SettlementReveal.NAMED_BALLOTS:
        ballots = tuple(
            RevealedBallot(member_id=member_id, option_id=submission.option_id)
            for member_id, submission in zip(
                state.room.required_member_ids,
                submissions,
                strict=True,
            )
        )
    elif settlement_definition.reveal is SettlementReveal.AGGREGATE:
        option_counts = tuple(
            RevealedOptionCount(option_id=option.id, count=counts[option.id])
            for option in settlement_definition.options
        )
    completed_settlement = next_settlement.model_copy(
        update={
            "outcome_id": outcome_id,
            "revealed": True,
            "revealed_ballots": ballots,
            "revealed_option_counts": option_counts,
        }
    )
    return _complete_settlement(
        state,
        definition=definition,
        settlement=completed_settlement,
        private_by_member=private_by_member,
        outcome_id=outcome_id,
    )


def _confirm_shared_choice(
    state: GameStateV2,
    command: ConfirmSharedChoiceCommand,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    settlement_definition = definition.settlement
    if isinstance(settlement_definition, SharedChoiceSettlementDefinition):
        pass
    elif isinstance(settlement_definition, FinalJudgmentSettlementDefinition):
        if settlement_definition.answer_mode is not FinalAnswerMode.SHARED_CHOICE:
            raise InvalidStageTransitionError("final judgment is not a shared choice")
    else:
        raise InvalidStageTransitionError("shared confirmation requires a shared-choice settlement")

    settlement = _require_settlement(state, command.payload.settlement_id)
    if state.stage.phase is not StagePhase.SETTLE:
        raise InvalidStageTransitionError("shared confirmation requires settle phase")
    option = _find_option(settlement_definition.options, command.payload.option_id)

    if settlement.shared_option_id != option.id:
        submitted_member_ids = (actor_member_id,)
    else:
        submitted_member_ids = _canonical_members(
            state,
            (*settlement.submitted_member_ids, actor_member_id),
        )
    next_settlement = settlement.model_copy(
        update={
            "shared_option_id": option.id,
            "submitted_member_ids": submitted_member_ids,
        }
    )
    if submitted_member_ids != state.room.required_member_ids:
        return _copy_with_stage_updates(state, settlement=next_settlement)

    outcome_id = _option_outcome_id(option)
    completed_settlement = next_settlement.model_copy(
        update={"outcome_id": outcome_id, "revealed": True}
    )
    return _complete_settlement(
        state,
        definition=definition,
        settlement=completed_settlement,
        private_by_member=state.private_by_member,
        outcome_id=outcome_id,
    )


def _request_hint(
    state: GameStateV2,
    command: HintRequestCommand,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    if state.stage.phase is not StagePhase.DISCUSS:
        raise InvalidStageTransitionError("hints can be requested only during discuss phase")
    hint_index, hint_state = _find_hint(state, definition, command.payload.hint_id)
    if hint_state.pending_level is not None:
        raise InvalidStageTransitionError("this hint already has a pending level")
    if command.payload.level != hint_state.revealed_level + 1:
        raise InvalidStageTransitionError("hint levels must be requested sequentially")

    next_hint = hint_state.model_copy(
        update={
            "pending_level": command.payload.level,
            "confirming_member_ids": (actor_member_id,),
        }
    )
    next_hint = _finish_hint_if_unanimous(state, next_hint)
    return _replace_hint(state, hint_index, next_hint)


def _confirm_hint(
    state: GameStateV2,
    command: HintConfirmCommand,
    actor_member_id: str,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    if state.stage.phase is not StagePhase.DISCUSS:
        raise InvalidStageTransitionError("hints can be confirmed only during discuss phase")
    hint_index, hint_state = _find_hint(state, definition, command.payload.hint_id)
    if hint_state.pending_level != command.payload.level:
        raise InvalidStageTransitionError("hint confirmation must match the pending level")

    confirming_member_ids = _canonical_members(
        state,
        (*hint_state.confirming_member_ids, actor_member_id),
    )
    next_hint = hint_state.model_copy(update={"confirming_member_ids": confirming_member_ids})
    next_hint = _finish_hint_if_unanimous(state, next_hint)
    return _replace_hint(state, hint_index, next_hint)


def _find_hint(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    hint_id: str,
) -> tuple[int, HintRuntimeState]:
    authored_hint_ids = tuple(hint.id for hint in definition.hints)
    if hint_id not in authored_hint_ids:
        raise InvalidStageTransitionError("hint_id is not declared by the current stage")
    for index, hint_state in enumerate(state.stage.hints):
        if hint_state.hint_id == hint_id:
            return index, hint_state
    raise InvalidStageTransitionError("hint runtime state is missing")


def _finish_hint_if_unanimous(
    state: GameStateV2,
    hint: HintRuntimeState,
) -> HintRuntimeState:
    if hint.confirming_member_ids != state.room.required_member_ids:
        return hint
    if hint.pending_level is None:
        raise InvalidStageTransitionError("cannot reveal a hint without a pending level")
    return hint.model_copy(
        update={
            "revealed_level": hint.pending_level,
            "pending_level": None,
            "confirming_member_ids": (),
        }
    )


def _replace_hint(
    state: GameStateV2,
    hint_index: int,
    hint: HintRuntimeState,
) -> GameStateV2:
    hints = list(state.stage.hints)
    hints[hint_index] = hint
    return _copy_with_stage_updates(state, hints=tuple(hints))


def _complete_settlement(
    state: GameStateV2,
    *,
    definition: MultiplayerStageDefinition,
    settlement: SettlementRuntimeState,
    private_by_member: dict[str, PrivatePlayerState],
    outcome_id: str,
) -> GameStateV2:
    revealed_material_ids = _material_ids_for_triggers(
        definition,
        {
            "stage_enter",
            "all_players_read",
            "settlement_done",
            f"outcome:{outcome_id}",
        },
    )
    stage = state.stage.model_copy(
        update={
            "phase": StagePhase.REVEAL,
            "settlement": settlement,
            "revealed_material_ids": revealed_material_ids,
        }
    )
    return _copy_state(state, private_by_member=private_by_member, stage=stage)


def _require_settlement(
    state: GameStateV2,
    settlement_id: str,
) -> SettlementRuntimeState:
    settlement = state.stage.settlement
    if settlement is None or settlement.settlement_id != settlement_id:
        raise InvalidStageTransitionError("settlement_id does not match the current settlement")
    return settlement


def _require_private_submission(
    private_state: PrivatePlayerState,
    *,
    settlement_id: str,
) -> PrivateSettlementSubmission:
    submission = private_state.settlement_submission
    if submission is None or submission.settlement_id != settlement_id:
        raise InvalidStageTransitionError("submitted member is missing a private settlement choice")
    return submission


def _find_option(options: tuple[SettlementOption, ...], option_id: str) -> SettlementOption:
    for option in options:
        if option.id == option_id:
            return option
    raise InvalidStageTransitionError("option_id is not declared by the current settlement")


def _option_outcome_id(option: SettlementOption) -> str:
    outcome_id = getattr(option, "outcome_id", None)
    if not isinstance(outcome_id, str) or not outcome_id:
        raise InvalidStageTransitionError("settlement option is missing outcome_id")
    return outcome_id


def _tie_outcome_id(
    definition: SecretVoteSettlementDefinition | FinalJudgmentSettlementDefinition,
) -> str:
    outcome_id = getattr(definition, "tie_outcome_id", None)
    if not isinstance(outcome_id, str) or not outcome_id:
        raise InvalidStageTransitionError("individual secret settlement is missing tie_outcome_id")
    return outcome_id


def _material_ids_for_triggers(
    definition: MultiplayerStageDefinition,
    triggers: set[str],
) -> tuple[str, ...]:
    return tuple(
        material.id for material in definition.public_materials if material.reveal_at in triggers
    )


def _copy_with_stage_updates(state: GameStateV2, **updates: object) -> GameStateV2:
    return _copy_state(state, stage=state.stage.model_copy(update=updates))


def _copy_state(
    state: GameStateV2,
    *,
    private_by_member: dict[str, PrivatePlayerState] | None = None,
    stage: StageRuntimeState,
) -> GameStateV2:
    updates: dict[str, object] = {"stage": stage}
    if private_by_member is not None:
        updates["private_by_member"] = {
            member_id: private_by_member[member_id] for member_id in state.room.required_member_ids
        }
    next_state = state.model_copy(update=updates)
    # model_copy does not revalidate nested updates; this keeps the reducer boundary strict.
    return GameStateV2.model_validate(next_state.model_dump())
