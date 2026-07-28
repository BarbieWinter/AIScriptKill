"""Headless specifications for the Multiplayer v1 offline state machine."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from engine.contracts.multiplayer_v1.authoring import (
    DiscussionDefinition,
    FinalJudgmentSettlementDefinition,
    HintDefinition,
    MultiplayerStageDefinition,
    NoSettlementDefinition,
    PublicMaterialDefinition,
    SecretVoteSettlementDefinition,
    SettlementOption,
    SharedChoiceSettlementDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    ConfirmDiscussionCloseCommand,
    ConfirmReadCommand,
    ConfirmSharedChoiceCommand,
    ConfirmSharedChoicePayload,
    HintConfirmCommand,
    HintConfirmPayload,
    HintRequestCommand,
    HintRequestPayload,
    RevokeDiscussionCloseCommand,
    StageCommandPayload,
    SubmitSettlementCommand,
    SubmitSettlementPayload,
)
from engine.contracts.multiplayer_v1.snapshots import build_participant_snapshot
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    HintRuntimeState,
    PlayerState,
    PrivatePlayerState,
    RevealedBallot,
    RevealedOptionCount,
    RoomState,
    SettlementRuntimeState,
    StageRuntimeState,
)
from engine.contracts.multiplayer_v1.vocabulary import (
    FinalAnswerMode,
    RoomStatus,
    SettlementMode,
    SettlementReveal,
    StagePhase,
    SubmissionChangePolicy,
)
from engine.core.multiplayer_state_machine import (
    InvalidStageTransitionError,
    complete_final_judgment,
    enter_next_stage,
    initialize_stage_runtime,
    reduce_stage_command,
)

SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
COMMAND_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEMBERS = ("member-a", "member-b")


def _materials() -> tuple[PublicMaterialDefinition, ...]:
    # Authored order intentionally differs from reveal chronology.
    return (
        PublicMaterialDefinition(id="read-clue", reveal_at="all_players_read"),
        PublicMaterialDefinition(id="opening", reveal_at="stage_enter"),
        PublicMaterialDefinition(id="alpha-proof", reveal_at="outcome:alpha"),
        PublicMaterialDefinition(id="settlement-summary", reveal_at="settlement_done"),
        PublicMaterialDefinition(id="tie-proof", reveal_at="outcome:tie"),
        PublicMaterialDefinition(id="beta-proof", reveal_at="outcome:beta"),
    )


def _options() -> tuple[SettlementOption, ...]:
    return (
        SettlementOption(id="option-a", text="甲", outcome_id="alpha"),
        SettlementOption(id="option-b", text="乙", outcome_id="beta"),
    )


def _secret_stage(
    stage_id: str = "stage-1",
    *,
    reveal: SettlementReveal = SettlementReveal.NAMED_BALLOTS,
) -> MultiplayerStageDefinition:
    return MultiplayerStageDefinition(
        id=stage_id,
        chapters={"character-a": f"chapter-a-{stage_id}", "character-b": f"chapter-b-{stage_id}"},
        public_materials=_materials(),
        discussion=DiscussionDefinition(),
        settlement=SecretVoteSettlementDefinition(
            mode=SettlementMode.SECRET_VOTE,
            settlement_id=f"vote-{stage_id}",
            question="谁更可疑？",
            options=_options(),
            tie_outcome_id="tie",
            reveal=reveal,
        ),
        hints=(HintDefinition(id="timeline", levels=("一", "二", "三")),),
    )


def _shared_stage(stage_id: str = "stage-shared") -> MultiplayerStageDefinition:
    return MultiplayerStageDefinition(
        id=stage_id,
        chapters={"character-a": f"chapter-a-{stage_id}", "character-b": f"chapter-b-{stage_id}"},
        public_materials=_materials(),
        discussion=DiscussionDefinition(),
        settlement=SharedChoiceSettlementDefinition(
            mode=SettlementMode.SHARED_CHOICE,
            settlement_id=f"choice-{stage_id}",
            question="共同答案？",
            options=_options(),
        ),
        hints=(HintDefinition(id="timeline", levels=("一", "二", "三")),),
    )


def _no_settlement_stage(stage_id: str = "stage-none") -> MultiplayerStageDefinition:
    return MultiplayerStageDefinition(
        id=stage_id,
        chapters={"character-a": f"chapter-a-{stage_id}", "character-b": f"chapter-b-{stage_id}"},
        public_materials=_materials(),
        discussion=DiscussionDefinition(),
        settlement=NoSettlementDefinition(mode=SettlementMode.NONE),
        hints=(),
    )


def _final_stage(answer_mode: FinalAnswerMode) -> MultiplayerStageDefinition:
    return MultiplayerStageDefinition(
        id="stage-final",
        chapters={
            "character-a": "chapter-a-final",
            "character-b": "chapter-b-final",
        },
        public_materials=_materials(),
        discussion=DiscussionDefinition(),
        settlement=FinalJudgmentSettlementDefinition(
            mode=SettlementMode.FINAL_JUDGMENT,
            settlement_id="final-choice",
            question="最终结论？",
            answer_mode=answer_mode,
            options=_options(),
            tie_outcome_id="tie" if answer_mode is FinalAnswerMode.INDIVIDUAL_SECRET else None,
            ending_by_outcome={
                "alpha": "ending-alpha",
                "beta": "ending-beta",
                **(
                    {"tie": "ending-tie"}
                    if answer_mode is FinalAnswerMode.INDIVIDUAL_SECRET
                    else {}
                ),
            },
            submission_change=(
                SubmissionChangePolicy.FORBIDDEN
                if answer_mode is FinalAnswerMode.INDIVIDUAL_SECRET
                else SubmissionChangePolicy.ALLOWED_BEFORE_COMPLETE
            ),
        ),
        hints=(),
    )


def _state(definition: MultiplayerStageDefinition) -> GameStateV2:
    return GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=SESSION_ID,
        room_revision=7,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=MEMBERS,
            current_stage_id=definition.id,
        ),
        players={
            "member-a": PlayerState(member_id="member-a", character_id="character-a", ready=True),
            "member-b": PlayerState(member_id="member-b", character_id="character-b", ready=True),
        },
        private_by_member={
            "member-a": PrivatePlayerState(
                character_id="character-a",
                unlocked_chapter_ids=(definition.chapters["character-a"],),
            ),
            "member-b": PrivatePlayerState(
                character_id="character-b",
                unlocked_chapter_ids=(definition.chapters["character-b"],),
            ),
        },
        stage=initialize_stage_runtime(definition, required_member_ids=MEMBERS),
    )


def _confirm_read(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    actor: str,
) -> GameStateV2:
    return reduce_stage_command(
        state,
        ConfirmReadCommand(
            command_id=COMMAND_ID,
            expected_revision=state.room_revision,
            type="stage.confirm_read",
            payload=StageCommandPayload(stage_id=definition.id),
        ),
        actor_member_id=actor,
        definition=definition,
    )


def _confirm_close(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    actor: str,
) -> GameStateV2:
    return reduce_stage_command(
        state,
        ConfirmDiscussionCloseCommand(
            command_id=COMMAND_ID,
            expected_revision=state.room_revision,
            type="discussion.confirm_close",
            payload=StageCommandPayload(stage_id=definition.id),
        ),
        actor_member_id=actor,
        definition=definition,
    )


def _to_discuss(definition: MultiplayerStageDefinition) -> GameStateV2:
    after_a = _confirm_read(_state(definition), definition, "member-a")
    return _confirm_read(after_a, definition, "member-b")


def _to_settle(definition: MultiplayerStageDefinition) -> GameStateV2:
    return _confirm_close(
        _confirm_close(_to_discuss(definition), definition, "member-a"),
        definition,
        "member-b",
    )


def _submit(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    actor: str,
    option_id: str,
) -> GameStateV2:
    settlement = definition.settlement
    assert not isinstance(settlement, NoSettlementDefinition)
    return reduce_stage_command(
        state,
        SubmitSettlementCommand(
            command_id=COMMAND_ID,
            expected_revision=state.room_revision,
            type="settlement.submit",
            payload=SubmitSettlementPayload(
                settlement_id=settlement.settlement_id,
                option_id=option_id,
            ),
        ),
        actor_member_id=actor,
        definition=definition,
    )


def _confirm_shared(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
    actor: str,
    option_id: str,
) -> GameStateV2:
    settlement = definition.settlement
    assert not isinstance(settlement, NoSettlementDefinition)
    return reduce_stage_command(
        state,
        ConfirmSharedChoiceCommand(
            command_id=COMMAND_ID,
            expected_revision=state.room_revision,
            type="settlement.confirm_shared_choice",
            payload=ConfirmSharedChoicePayload(
                settlement_id=settlement.settlement_id,
                option_id=option_id,
            ),
        ),
        actor_member_id=actor,
        definition=definition,
    )


def test_state_contract_requires_complete_private_map_and_canonical_member_order() -> None:
    state = _state(_secret_stage())

    with pytest.raises(ValidationError, match="private_by_member keys"):
        GameStateV2.model_validate(
            state.model_copy(
                update={"private_by_member": {"member-a": state.private_by_member["member-a"]}}
            ).model_dump()
        )

    with pytest.raises(ValidationError, match="canonical room member order"):
        GameStateV2.model_validate(
            state.model_copy(
                update={
                    "stage": state.stage.model_copy(
                        update={"read_member_ids": tuple(reversed(MEMBERS))}
                    )
                }
            ).model_dump()
        )


def test_state_contract_validates_hint_and_revealed_ballot_shapes() -> None:
    settlement = SettlementRuntimeState(
        settlement_id="vote-1",
        mode=SettlementMode.SECRET_VOTE,
        required_member_ids=MEMBERS,
        submitted_member_ids=MEMBERS,
        outcome_id="alpha",
        revealed=True,
        revealed_ballots=(
            RevealedBallot(member_id="member-a", option_id="option-a"),
            RevealedBallot(member_id="member-b", option_id="option-b"),
        ),
    )
    state = _state(_secret_stage()).model_copy(
        update={
            "stage": StageRuntimeState(
                stage_id="stage-1",
                phase=StagePhase.REVEAL,
                read_member_ids=MEMBERS,
                discussion_close_member_ids=MEMBERS,
                settlement=settlement,
            )
        }
    )
    assert GameStateV2.model_validate(state.model_dump()).stage.settlement == settlement

    with pytest.raises(ValidationError, match="next sequential level"):
        HintRuntimeState(hint_id="timeline", revealed_level=1, pending_level=3)

    with pytest.raises(ValidationError, match="canonical required-member order"):
        GameStateV2.model_validate(
            state.model_copy(
                update={
                    "stage": state.stage.model_copy(
                        update={
                            "settlement": settlement.model_copy(
                                update={
                                    "revealed_ballots": tuple(reversed(settlement.revealed_ballots))
                                }
                            )
                        }
                    )
                }
            ).model_dump()
        )


def test_read_barrier_is_locked_pure_and_order_independent() -> None:
    definition = _secret_stage()
    initial = _state(definition)
    initial_json = initial.model_dump_json()

    after_a = _confirm_read(initial, definition, "member-a")
    assert after_a.stage.phase is StagePhase.READ
    assert after_a.stage.read_member_ids == ("member-a",)
    assert after_a.stage.revealed_material_ids == ("opening",)
    assert after_a.room_revision == initial.room_revision
    assert initial.model_dump_json() == initial_json

    repeated = _confirm_read(after_a, definition, "member-a")
    assert repeated == after_a

    a_then_b = _confirm_read(after_a, definition, "member-b")
    after_b = _confirm_read(initial, definition, "member-b")
    b_then_a = _confirm_read(after_b, definition, "member-a")
    assert a_then_b == b_then_a
    assert a_then_b.stage.phase is StagePhase.DISCUSS
    assert a_then_b.stage.read_member_ids == MEMBERS
    assert a_then_b.stage.revealed_material_ids == ("read-clue", "opening")

    with pytest.raises(InvalidStageTransitionError, match="read phase"):
        _confirm_read(a_then_b, definition, "member-a")


def test_reducer_rejects_untrusted_actor_and_mismatched_ids() -> None:
    definition = _secret_stage()
    state = _state(definition)
    command = ConfirmReadCommand(
        command_id=COMMAND_ID,
        expected_revision=7,
        type="stage.confirm_read",
        payload=StageCommandPayload(stage_id="wrong-stage"),
    )
    with pytest.raises(InvalidStageTransitionError, match="actor"):
        reduce_stage_command(
            state,
            command,
            actor_member_id="outsider",
            definition=definition,
        )
    with pytest.raises(InvalidStageTransitionError, match="stage_id"):
        reduce_stage_command(
            state,
            command,
            actor_member_id="member-a",
            definition=definition,
        )


def test_discussion_close_requires_every_member_and_is_revocable() -> None:
    definition = _secret_stage()
    discussing = _to_discuss(definition)
    after_a = _confirm_close(discussing, definition, "member-a")
    assert after_a.stage.phase is StagePhase.DISCUSS

    revoked = reduce_stage_command(
        after_a,
        RevokeDiscussionCloseCommand(
            command_id=COMMAND_ID,
            expected_revision=7,
            type="discussion.revoke_close",
            payload=StageCommandPayload(stage_id=definition.id),
        ),
        actor_member_id="member-a",
        definition=definition,
    )
    assert revoked.stage.discussion_close_member_ids == ()

    settling = _confirm_close(after_a, definition, "member-b")
    assert settling.stage.phase is StagePhase.SETTLE
    assert settling.stage.discussion_close_member_ids == MEMBERS
    with pytest.raises(InvalidStageTransitionError, match="discuss phase"):
        reduce_stage_command(
            settling,
            RevokeDiscussionCloseCommand(
                command_id=COMMAND_ID,
                expected_revision=7,
                type="discussion.revoke_close",
                payload=StageCommandPayload(stage_id=definition.id),
            ),
            actor_member_id="member-a",
            definition=definition,
        )


def test_no_settlement_close_enters_observable_reveal_atomically() -> None:
    definition = _no_settlement_stage()
    discussing = _to_discuss(definition)
    after_a = _confirm_close(discussing, definition, "member-a")
    revealed = _confirm_close(after_a, definition, "member-b")

    assert after_a.stage.phase is StagePhase.DISCUSS
    assert revealed.stage.phase is StagePhase.REVEAL
    assert revealed.stage.settlement is None
    assert revealed.stage.revealed_material_ids == (
        "read-clue",
        "opening",
        "settlement-summary",
    )


def test_secret_submissions_stay_private_until_atomic_named_reveal() -> None:
    definition = _secret_stage()
    settling = _to_settle(definition)
    settling_json = settling.model_dump_json()

    after_a = _submit(settling, definition, "member-a", "option-a")
    settlement = after_a.stage.settlement
    assert settlement is not None
    assert settlement.submitted_member_ids == ("member-a",)
    assert settlement.shared_option_id is None
    assert settlement.outcome_id is None
    assert settlement.revealed_ballots == ()
    assert after_a.private_by_member["member-a"].settlement_submission is not None
    assert after_a.private_by_member["member-b"].settlement_submission is None
    assert settling.model_dump_json() == settling_json

    member_b_snapshot = build_participant_snapshot(
        after_a,
        member_id="member-b",
        event_head_sequence=0,
    ).model_dump_json()
    assert "option-a" not in member_b_snapshot

    with pytest.raises(InvalidStageTransitionError, match="cannot be changed"):
        _submit(after_a, definition, "member-a", "option-b")

    revealed = _submit(after_a, definition, "member-b", "option-b")
    completed = revealed.stage.settlement
    assert completed is not None
    assert revealed.stage.phase is StagePhase.REVEAL
    assert completed.outcome_id == "tie"
    assert completed.revealed is True
    assert completed.revealed_ballots == (
        RevealedBallot(member_id="member-a", option_id="option-a"),
        RevealedBallot(member_id="member-b", option_id="option-b"),
    )
    assert completed.revealed_option_counts == ()
    assert revealed.stage.revealed_material_ids == (
        "read-clue",
        "opening",
        "settlement-summary",
        "tie-proof",
    )
    assert revealed.room_revision == settling.room_revision


def test_aggregate_reveal_publishes_canonical_authored_option_counts() -> None:
    definition = _secret_stage(reveal=SettlementReveal.AGGREGATE)
    settling = _to_settle(definition)

    revealed = _submit(
        _submit(settling, definition, "member-b", "option-a"),
        definition,
        "member-a",
        "option-a",
    )

    settlement = revealed.stage.settlement
    assert settlement is not None
    assert settlement.revealed_ballots == ()
    assert settlement.revealed_option_counts == (
        RevealedOptionCount(option_id="option-a", count=2),
        RevealedOptionCount(option_id="option-b", count=0),
    )


def test_outcome_only_reveal_publishes_neither_ballots_nor_counts() -> None:
    definition = _secret_stage(reveal=SettlementReveal.OUTCOME_ONLY)
    settling = _to_settle(definition)

    revealed = _submit(
        _submit(settling, definition, "member-a", "option-a"),
        definition,
        "member-b",
        "option-b",
    )

    settlement = revealed.stage.settlement
    assert settlement is not None
    assert settlement.outcome_id == "tie"
    assert settlement.revealed_ballots == ()
    assert settlement.revealed_option_counts == ()


def test_revealed_settlement_contract_rejects_incomplete_or_ambiguous_public_results() -> None:
    with pytest.raises(ValidationError, match="all required submissions"):
        SettlementRuntimeState(
            settlement_id="vote-1",
            mode=SettlementMode.SECRET_VOTE,
            required_member_ids=MEMBERS,
            submitted_member_ids=("member-a",),
            outcome_id="alpha",
            revealed=True,
        )

    with pytest.raises(ValidationError, match="mutually exclusive"):
        SettlementRuntimeState(
            settlement_id="vote-1",
            mode=SettlementMode.SECRET_VOTE,
            required_member_ids=MEMBERS,
            submitted_member_ids=MEMBERS,
            outcome_id="alpha",
            revealed=True,
            revealed_ballots=(
                RevealedBallot(member_id="member-a", option_id="option-a"),
                RevealedBallot(member_id="member-b", option_id="option-a"),
            ),
            revealed_option_counts=(RevealedOptionCount(option_id="option-a", count=2),),
        )

    with pytest.raises(ValidationError, match="sum to submitted members"):
        SettlementRuntimeState(
            settlement_id="vote-1",
            mode=SettlementMode.SECRET_VOTE,
            required_member_ids=MEMBERS,
            submitted_member_ids=MEMBERS,
            outcome_id="alpha",
            revealed=True,
            revealed_option_counts=(RevealedOptionCount(option_id="option-a", count=1),),
        )


def test_secret_submission_order_has_canonical_equivalent_final_state_and_unique_winner() -> None:
    definition = _secret_stage()
    settling = _to_settle(definition)

    a_then_b = _submit(
        _submit(settling, definition, "member-a", "option-a"),
        definition,
        "member-b",
        "option-a",
    )
    b_then_a = _submit(
        _submit(settling, definition, "member-b", "option-a"),
        definition,
        "member-a",
        "option-a",
    )

    assert a_then_b == b_then_a
    settlement = a_then_b.stage.settlement
    assert settlement is not None
    assert settlement.outcome_id == "alpha"
    assert settlement.submitted_member_ids == MEMBERS
    assert a_then_b.stage.revealed_material_ids == (
        "read-clue",
        "opening",
        "alpha-proof",
        "settlement-summary",
    )


def test_shared_choice_exposes_candidate_and_switching_resets_confirmations() -> None:
    definition = _shared_stage()
    settling = _to_settle(definition)

    proposed = _confirm_shared(settling, definition, "member-a", "option-a")
    proposal = proposed.stage.settlement
    assert proposal is not None
    assert proposal.shared_option_id == "option-a"
    assert proposal.submitted_member_ids == ("member-a",)
    assert all(
        private_state.settlement_submission is None
        for private_state in proposed.private_by_member.values()
    )

    switched = _confirm_shared(proposed, definition, "member-b", "option-b")
    switched_settlement = switched.stage.settlement
    assert switched_settlement is not None
    assert switched_settlement.shared_option_id == "option-b"
    assert switched_settlement.submitted_member_ids == ("member-b",)
    assert switched.stage.phase is StagePhase.SETTLE

    revealed = _confirm_shared(switched, definition, "member-a", "option-b")
    completed = revealed.stage.settlement
    assert completed is not None
    assert revealed.stage.phase is StagePhase.REVEAL
    assert completed.submitted_member_ids == MEMBERS
    assert completed.outcome_id == "beta"
    assert completed.revealed_ballots == ()


def test_final_judgment_dispatches_and_completes_with_authored_ending_mapping() -> None:
    individual = _final_stage(FinalAnswerMode.INDIVIDUAL_SECRET)
    individual_settling = _to_settle(individual)
    with pytest.raises(InvalidStageTransitionError, match="shared choice"):
        _confirm_shared(individual_settling, individual, "member-a", "option-a")
    individual_revealed = _submit(
        _submit(individual_settling, individual, "member-a", "option-a"),
        individual,
        "member-b",
        "option-b",
    )
    assert individual_revealed.stage.phase is StagePhase.REVEAL

    shared = _final_stage(FinalAnswerMode.SHARED_CHOICE)
    shared_settling = _to_settle(shared)
    with pytest.raises(InvalidStageTransitionError, match="individual secret"):
        _submit(shared_settling, shared, "member-a", "option-a")
    shared_revealed = _confirm_shared(
        _confirm_shared(shared_settling, shared, "member-a", "option-a"),
        shared,
        "member-b",
        "option-a",
    )

    completed = complete_final_judgment(
        shared_revealed,
        definition=shared,
    )

    assert completed.room.status is RoomStatus.COMPLETED
    assert completed.ending_id == "ending-alpha"
    assert completed.stage.phase is StagePhase.REVEAL
    assert completed.stage.settlement is not None
    assert completed.stage.settlement.outcome_id == "alpha"
    assert shared_revealed.room.status is RoomStatus.ACTIVE
    assert shared_revealed.ending_id is None

    incomplete_settlement = shared.settlement.model_copy(
        update={"ending_by_outcome": {"beta": "ending-beta"}}
    )
    incomplete_definition = shared.model_copy(update={"settlement": incomplete_settlement})
    with pytest.raises(InvalidStageTransitionError, match="authored ending"):
        complete_final_judgment(
            shared_revealed,
            definition=incomplete_definition,
        )
    with pytest.raises(InvalidStageTransitionError, match="branch"):
        enter_next_stage(
            shared_revealed,
            current_definition=shared,
            next_definition=_secret_stage("after-final"),
        )


@pytest.mark.parametrize(
    ("option_id", "expected_outcome_id", "expected_ending_id"),
    (
        ("option-a", "alpha", "ending-alpha"),
        ("option-b", "beta", "ending-beta"),
    ),
)
def test_each_final_outcome_selects_its_authored_ending(
    option_id: str,
    expected_outcome_id: str,
    expected_ending_id: str,
) -> None:
    definition = _final_stage(FinalAnswerMode.SHARED_CHOICE)
    settling = _to_settle(definition)
    revealed = _confirm_shared(
        _confirm_shared(settling, definition, "member-a", option_id),
        definition,
        "member-b",
        option_id,
    )

    completed = complete_final_judgment(
        revealed,
        definition=definition,
    )

    assert completed.stage.settlement is not None
    assert completed.stage.settlement.outcome_id == expected_outcome_id
    assert completed.ending_id == expected_ending_id


def test_hints_require_sequential_unanimous_confirmation() -> None:
    definition = _secret_stage()
    discussing = _to_discuss(definition)

    def request(state: GameStateV2, actor: str, level: int) -> GameStateV2:
        return reduce_stage_command(
            state,
            HintRequestCommand(
                command_id=COMMAND_ID,
                expected_revision=7,
                type="hint.request",
                payload=HintRequestPayload(hint_id="timeline", level=level),
            ),
            actor_member_id=actor,
            definition=definition,
        )

    def confirm(state: GameStateV2, actor: str, level: int) -> GameStateV2:
        return reduce_stage_command(
            state,
            HintConfirmCommand(
                command_id=COMMAND_ID,
                expected_revision=7,
                type="hint.confirm",
                payload=HintConfirmPayload(hint_id="timeline", level=level),
            ),
            actor_member_id=actor,
            definition=definition,
        )

    with pytest.raises(InvalidStageTransitionError, match="only during discuss"):
        request(_state(definition), "member-a", 1)

    with pytest.raises(InvalidStageTransitionError, match="sequentially"):
        request(discussing, "member-a", 2)

    pending = request(discussing, "member-b", 1)
    assert pending.stage.hints[0] == HintRuntimeState(
        hint_id="timeline",
        pending_level=1,
        confirming_member_ids=("member-b",),
    )
    with pytest.raises(InvalidStageTransitionError, match="match the pending"):
        confirm(pending, "member-a", 2)

    level_one = confirm(pending, "member-a", 1)
    assert level_one.stage.hints[0] == HintRuntimeState(hint_id="timeline", revealed_level=1)

    level_two_pending = request(level_one, "member-a", 2)
    level_two = confirm(level_two_pending, "member-b", 2)
    assert level_two.stage.hints[0].revealed_level == 2
    assert level_two.stage.hints[0].pending_level is None
    assert level_two.stage.hints[0].confirming_member_ids == ()


def test_enter_next_stage_rejects_incomplete_active_settlement_bypass() -> None:
    current = _secret_stage()
    settling = _to_settle(current)
    forged_reveal = settling.model_copy(
        update={"stage": settling.stage.model_copy(update={"phase": StagePhase.REVEAL})}
    )

    with pytest.raises(InvalidStageTransitionError, match="completed and revealed"):
        enter_next_stage(
            forged_reveal,
            current_definition=current,
            next_definition=_shared_stage("stage-2"),
        )


def test_enter_next_stage_allows_completed_no_settlement_reveal() -> None:
    current = _no_settlement_stage()
    revealed = _confirm_close(
        _confirm_close(_to_discuss(current), current, "member-a"),
        current,
        "member-b",
    )

    advanced = enter_next_stage(
        revealed,
        current_definition=current,
        next_definition=_shared_stage("stage-2"),
    )
    assert advanced.stage.stage_id == "stage-2"
    assert advanced.stage.phase is StagePhase.READ


def test_enter_next_stage_unlocks_mapped_chapters_and_initializes_runtime() -> None:
    current = _secret_stage()
    settling = _to_settle(current)
    revealed = _submit(
        _submit(settling, current, "member-a", "option-a"),
        current,
        "member-b",
        "option-a",
    )
    revealed_json = revealed.model_dump_json()
    next_definition = _shared_stage("stage-2")

    advanced = enter_next_stage(
        revealed,
        current_definition=current,
        next_definition=next_definition,
    )

    assert revealed.model_dump_json() == revealed_json
    assert advanced.room_revision == revealed.room_revision
    assert advanced.room.current_stage_id == "stage-2"
    assert advanced.stage == initialize_stage_runtime(
        next_definition,
        required_member_ids=MEMBERS,
    )
    assert advanced.stage.phase is StagePhase.READ
    assert advanced.stage.revealed_material_ids == ("opening",)
    assert advanced.prior_revealed_material_ids == revealed.stage.revealed_material_ids
    assert "alpha-proof" in advanced.prior_revealed_material_ids
    assert advanced.private_by_member["member-a"].unlocked_chapter_ids == (
        current.chapters["character-a"],
        next_definition.chapters["character-a"],
    )
    assert advanced.private_by_member["member-b"].unlocked_chapter_ids == (
        current.chapters["character-b"],
        next_definition.chapters["character-b"],
    )
    assert all(
        private_state.settlement_submission is None
        for private_state in advanced.private_by_member.values()
    )

    with pytest.raises(InvalidStageTransitionError, match="reveal phase"):
        enter_next_stage(
            settling,
            current_definition=current,
            next_definition=next_definition,
        )
