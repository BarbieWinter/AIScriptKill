"""Drive the real minimal two-player package through completion and review."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from engine.contracts.multiplayer_v1.authoring import (
    FinalJudgmentSettlementDefinition,
    MultiplayerStageDefinition,
    SecretVoteSettlementDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    ConfirmDiscussionCloseCommand,
    ConfirmReadCommand,
    ConfirmSharedChoiceCommand,
    ConfirmSharedChoicePayload,
    StageCommandPayload,
    SubmitSettlementCommand,
    SubmitSettlementPayload,
)
from engine.contracts.multiplayer_v1.snapshots import build_participant_snapshot
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus, StagePhase
from engine.core.multiplayer_review import (
    CompletedReviewProjectionError,
    project_completed_review,
)
from engine.core.multiplayer_state_machine import (
    complete_final_judgment,
    enter_next_stage,
    initialize_stage_runtime,
    reduce_stage_command,
)
from engine.core.package_loader import load_package_directory
from engine.core.package_multiplayer import multiplayer_stage_contract
from engine.core.package_schema import ScriptPackageImport
from engine.core.runtime_package_snapshot import (
    decode_runtime_package_snapshot,
    encode_runtime_package_snapshot,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"
SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
COMMAND_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
MEMBERS = ("member-a", "member-b")
CHARACTERS = {"member-a": "investigator", "member-b": "insider"}


def _initial_state(package: ScriptPackageImport) -> GameStateV2:
    investigation = multiplayer_stage_contract(package, "investigation")
    return GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=SESSION_ID,
        room_revision=1,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=MEMBERS,
            current_stage_id=investigation.id,
        ),
        players={
            member_id: PlayerState(
                member_id=member_id,
                character_id=character_id,
                ready=True,
            )
            for member_id, character_id in CHARACTERS.items()
        },
        private_by_member={
            member_id: PrivatePlayerState(
                character_id=character_id,
                unlocked_chapter_ids=(investigation.chapters[character_id],),
            )
            for member_id, character_id in CHARACTERS.items()
        },
        stage=initialize_stage_runtime(investigation, required_member_ids=MEMBERS),
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
            payload=StageCommandPayload(stage_id=state.stage.stage_id),
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
            payload=StageCommandPayload(stage_id=state.stage.stage_id),
        ),
        actor_member_id=actor,
        definition=definition,
    )


def _advance_to_settlement(
    state: GameStateV2,
    definition: MultiplayerStageDefinition,
) -> GameStateV2:
    for actor in MEMBERS:
        state = _confirm_read(state, definition, actor)
    for actor in MEMBERS:
        state = _confirm_close(state, definition, actor)
    return state


def test_real_two_player_package_completes_and_review_uses_frozen_truth() -> None:
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    frozen = encode_runtime_package_snapshot(package)
    room_package = decode_runtime_package_snapshot(frozen.payload, frozen.sha256)
    investigation = multiplayer_stage_contract(room_package, "investigation")
    final_judgment = multiplayer_stage_contract(room_package, "final-judgment")

    state = _advance_to_settlement(_initial_state(room_package), investigation)
    settlement = investigation.settlement
    assert isinstance(settlement, SecretVoteSettlementDefinition)
    for actor, option_id in zip(
        MEMBERS,
        ("investigator-account", "insider-account"),
        strict=True,
    ):
        state = reduce_stage_command(
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
            definition=investigation,
        )

    assert state.stage.phase is StagePhase.REVEAL
    assert state.stage.settlement is not None
    assert state.stage.settlement.outcome_id == "split-vote"
    state = enter_next_stage(
        state,
        current_definition=investigation,
        next_definition=final_judgment,
    )
    assert {
        member_id: private_state.unlocked_chapter_ids
        for member_id, private_state in state.private_by_member.items()
    } == {
        "member-a": ("investigator-investigation", "investigator-final-judgment"),
        "member-b": ("insider-investigation", "insider-final-judgment"),
    }

    with pytest.raises(CompletedReviewProjectionError, match="completed room"):
        project_completed_review(
            state=state,
            member_id="member-a",
            package=room_package,
            final_definition=final_judgment,
        )

    state = _advance_to_settlement(state, final_judgment)
    final_settlement = final_judgment.settlement
    assert isinstance(final_settlement, FinalJudgmentSettlementDefinition)
    for actor in MEMBERS:
        state = reduce_stage_command(
            state,
            ConfirmSharedChoiceCommand(
                command_id=COMMAND_ID,
                expected_revision=state.room_revision,
                type="settlement.confirm_shared_choice",
                payload=ConfirmSharedChoicePayload(
                    settlement_id=final_settlement.settlement_id,
                    option_id="timeline-conflict",
                ),
            ),
            actor_member_id=actor,
            definition=final_judgment,
        )

    completed = complete_final_judgment(
        state,
        definition=final_judgment,
        ending_ids=(ending.id for ending in room_package.endings),
    )
    review = project_completed_review(
        state=completed,
        member_id="member-a",
        package=room_package,
        final_definition=final_judgment,
    )

    assert completed.room.status is RoomStatus.COMPLETED
    assert review.ending.id == "conflicting-accounts"
    assert review.ending.outcome_text.startswith("你们确认知情人")
    assert review.truth.timeline[-1].hidden is True
    assert {chapter.id for chapter in review.chapters} == {
        "investigator-investigation",
        "insider-investigation",
        "investigator-final-judgment",
        "insider-final-judgment",
    }
    assert review.final_settlement.reveal == "outcome_only"
    review_json = review.model_dump_json()
    assert "ballots" not in review_json
    assert "option_counts" not in review_json

    with pytest.raises(CompletedReviewProjectionError, match="belong to the room"):
        project_completed_review(
            state=completed,
            member_id="outsider",
            package=room_package,
            final_definition=final_judgment,
        )
    with pytest.raises(CompletedReviewProjectionError, match="frozen truth"):
        project_completed_review(
            state=completed,
            member_id="member-a",
            package=replace(room_package, dm_guide={}),
            final_definition=final_judgment,
        )
    with pytest.raises(CompletedReviewProjectionError, match="exactly once"):
        project_completed_review(
            state=completed,
            member_id="member-a",
            package=replace(room_package, endings=()),
            final_definition=final_judgment,
        )

    participant_json = build_participant_snapshot(
        completed,
        member_id="member-a",
        event_head_sequence=0,
    ).model_dump_json()
    assert "private_by_member" not in participant_json
    assert "insider-investigation" not in participant_json
    assert "是否承认违规进入由你决定" not in participant_json
    assert "case_summary" not in participant_json
