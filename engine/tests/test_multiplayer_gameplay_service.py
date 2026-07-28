"""Exercise the Slim M2 gameplay service against the real frozen package."""

from __future__ import annotations

import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

import pytest

from engine.api.errors import ApiError
from engine.contracts.multiplayer_v1.authoring import (
    FinalJudgmentSettlementDefinition,
    SecretVoteSettlementDefinition,
)
from engine.contracts.multiplayer_v1.commands import (
    AdvanceStageCommand,
    ConfirmDiscussionCloseCommand,
    ConfirmReadCommand,
    ConfirmSharedChoiceCommand,
    ConfirmSharedChoicePayload,
    MultiplayerCommand,
    RoomResyncCommand,
    RoomResyncPayload,
    SendDiscussionMessageCommand,
    SendDiscussionMessagePayload,
    StageCommandPayload,
    SubmitSettlementCommand,
    SubmitSettlementPayload,
)
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus, StagePhase
from engine.core.multiplayer_state_machine import initialize_stage_runtime
from engine.core.package_loader import load_package_directory
from engine.core.package_multiplayer import multiplayer_stage_contract
from engine.core.runtime_package_snapshot import (
    decode_runtime_package_snapshot,
    encode_runtime_package_snapshot,
)
from engine.repositories.multiplayer_room_models import StoredMultiplayerRoom, StoredRoomMember
from engine.services.multiplayer_gameplay_service import (
    apply_gameplay_command,
    decode_room_game_state,
    project_gameplay_snapshot,
    project_multiplayer_review,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"
SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
MEMBER_IDS = (
    UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
)
CHARACTER_IDS = ("investigator", "insider")


def _active_room() -> tuple[StoredMultiplayerRoom, tuple[StoredRoomMember, ...]]:
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    snapshot = encode_runtime_package_snapshot(package)
    definition = multiplayer_stage_contract(package, "investigation")
    member_keys = tuple(str(member_id) for member_id in MEMBER_IDS)
    state = GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=SESSION_ID,
        room_revision=1,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=member_keys,
            current_stage_id=definition.id,
        ),
        players={
            member_id: PlayerState(
                member_id=member_id,
                character_id=character_id,
                ready=True,
            )
            for member_id, character_id in zip(
                member_keys,
                CHARACTER_IDS,
                strict=True,
            )
        },
        private_by_member={
            member_id: PrivatePlayerState(
                character_id=character_id,
                unlocked_chapter_ids=(definition.chapters[character_id],),
            )
            for member_id, character_id in zip(
                member_keys,
                CHARACTER_IDS,
                strict=True,
            )
        },
        stage=initialize_stage_runtime(
            definition,
            required_member_ids=member_keys,
        ),
    )
    now = datetime.now(UTC)
    room = StoredMultiplayerRoom(
        id=SESSION_ID,
        script_id=package.package.id,
        status="active",
        revision=1,
        event_head_sequence=0,
        state_schema_version=2,
        state=state.model_dump(mode="json"),
        runtime_package_version=package.package.version,
        runtime_package_snapshot=dict(snapshot.payload),
        runtime_package_sha256=snapshot.sha256,
        created_at=now,
        started_at=now,
        closed_at=None,
    )
    members = tuple(
        StoredRoomMember(
            id=member_id,
            session_id=SESSION_ID,
            principal_id=uuid4(),
            room_role="host" if index == 0 else "player",
            ready_at=now,
            joined_at=now,
        )
        for index, member_id in enumerate(MEMBER_IDS)
    )
    return room, members


def _legacy_final_stage_room() -> tuple[
    StoredMultiplayerRoom,
    tuple[StoredRoomMember, ...],
]:
    room, members = _active_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )
    state = decode_room_game_state(room)
    definition = multiplayer_stage_contract(package, "final-judgment")
    private_by_member = {
        member_id: private_state.model_copy(
            update={
                "unlocked_chapter_ids": (
                    private_state.unlocked_chapter_ids[0],
                    definition.chapters[private_state.character_id],
                )
            }
        )
        for member_id, private_state in state.private_by_member.items()
        if private_state.character_id is not None
    }
    legacy_state = GameStateV2.model_validate(
        state.model_copy(
            update={
                "room": state.room.model_copy(update={"current_stage_id": definition.id}),
                "private_by_member": private_by_member,
                "stage": initialize_stage_runtime(
                    definition,
                    required_member_ids=state.room.required_member_ids,
                ),
            }
        ).model_dump()
    )
    return replace(room, state=legacy_state.model_dump(mode="json")), members


def _apply(
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    command: MultiplayerCommand,
) -> StoredMultiplayerRoom:
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )
    mutation = apply_gameplay_command(
        room=room,
        member=member,
        command=command,
        package=package,
    )
    revision = room.revision + 1 if mutation.state_changed else room.revision
    sequence = room.event_head_sequence + 1 if mutation.event_required else room.event_head_sequence
    state = mutation.state.model_copy(update={"room_revision": revision})
    return replace(
        room,
        status=state.room.status.value,
        revision=revision,
        event_head_sequence=sequence,
        state=state.model_dump(mode="json"),
        closed_at=datetime.now(UTC) if state.room.status is RoomStatus.COMPLETED else None,
    )


def _stage_command(
    room: StoredMultiplayerRoom,
    command_type: Literal[
        "stage.confirm_read",
        "discussion.confirm_close",
        "stage.advance",
    ],
    stage_id: str,
) -> ConfirmReadCommand | ConfirmDiscussionCloseCommand | AdvanceStageCommand:
    payload = StageCommandPayload(stage_id=stage_id)
    if command_type == "stage.confirm_read":
        return ConfirmReadCommand(
            command_id=uuid4(),
            expected_revision=room.revision,
            type="stage.confirm_read",
            payload=payload,
        )
    if command_type == "discussion.confirm_close":
        return ConfirmDiscussionCloseCommand(
            command_id=uuid4(),
            expected_revision=room.revision,
            type="discussion.confirm_close",
            payload=payload,
        )
    return AdvanceStageCommand(
        command_id=uuid4(),
        expected_revision=room.revision,
        type="stage.advance",
        payload=payload,
    )


def test_snapshot_whitelists_private_content_and_validates_public_chat() -> None:
    room, members = _active_room()
    package = load_package_directory(PACKAGE_ROOT, publish=True)

    first = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    second = project_gameplay_snapshot(
        room=room,
        member=members[1],
        package=package,
        event_rows=(),
    )

    assert [chapter.id for chapter in first.chapters] == ["investigator-investigation"]
    assert [chapter.id for chapter in second.chapters] == ["insider-investigation"]
    assert first.settlement is None
    assert first.public_materials[0].id == "arrival-photo"
    assert first.public_materials[0].url is None
    serialized = first.model_dump_json()
    assert "private_by_member" not in serialized
    assert "insider-investigation" not in serialized
    assert "dm_guide" not in serialized
    assert "conflicting-accounts" not in serialized

    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "stage.confirm_read", "investigation"),
        )
    chat_command = SendDiscussionMessageCommand(
        command_id=uuid4(),
        expected_revision=room.revision,
        type="discussion.send_message",
        payload=SendDiscussionMessagePayload(
            stage_id="investigation",
            message_id=uuid4(),
            text="门锁没有损坏。",
        ),
    )
    mutation = apply_gameplay_command(
        room=room,
        member=members[0],
        command=chat_command,
        package=package,
    )
    assert mutation.state_changed is False
    assert mutation.event_required is True
    event = {
        "sequence": room.event_head_sequence + 1,
        "event_type": mutation.event_type,
        "payload": mutation.event_payload,
    }
    room = replace(room, event_head_sequence=room.event_head_sequence + 1)
    snapshot = project_gameplay_snapshot(
        room=room,
        member=members[1],
        package=package,
        event_rows=(event,),
    )
    assert snapshot.discussion_messages[0].member_id == str(members[0].id)
    assert snapshot.discussion_messages[0].character_id == "investigator"
    assert snapshot.discussion_messages[0].text == "门锁没有损坏。"

    invalid_payload = dict(mutation.event_payload)
    invalid_payload["character_id"] = "insider"
    with pytest.raises(ApiError) as exc_info:
        project_gameplay_snapshot(
            room=room,
            member=members[1],
            package=package,
            event_rows=({**event, "payload": invalid_payload},),
        )
    assert exc_info.value.error.code == "ROOM_EVENT_INVALID"


def test_snapshot_restores_deterministic_materials_for_legacy_advanced_room() -> None:
    room, members = _legacy_final_stage_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )

    snapshot = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )

    assert snapshot.stage_id == "final-judgment"
    assert [material.id for material in snapshot.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]


def test_next_mutation_keeps_v2_material_state_stage_local_for_legacy_room() -> None:
    room, members = _legacy_final_stage_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )

    mutation = apply_gameplay_command(
        room=room,
        member=members[0],
        command=_stage_command(room, "stage.confirm_read", "final-judgment"),
        package=package,
    )

    assert mutation.state_changed is True
    assert mutation.state.stage.revealed_material_ids == ()

    persisted = replace(
        room,
        revision=room.revision + 1,
        state=mutation.state.model_copy(update={"room_revision": room.revision + 1}).model_dump(
            mode="json"
        ),
    )
    snapshot = project_gameplay_snapshot(
        room=persisted,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert [material.id for material in snapshot.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]


def test_legacy_outcome_material_survives_stage_advance_and_redecode() -> None:
    room, members = _active_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )
    investigation_record = package.stages[0]
    investigation_definition = dict(investigation_record.definition)
    public_materials = [
        {
            **material,
            "reveal_at": (
                "outcome:trust-investigator"
                if material["id"] == "witness-note"
                else material["reveal_at"]
            ),
        }
        for material in investigation_definition["public_materials"]
    ]
    investigation_definition["public_materials"] = public_materials
    legacy_package = replace(
        package,
        stages=(
            replace(investigation_record, definition=investigation_definition),
            *package.stages[1:],
        ),
    )
    frozen = encode_runtime_package_snapshot(legacy_package)
    room = replace(
        room,
        runtime_package_snapshot=dict(frozen.payload),
        runtime_package_sha256=frozen.sha256,
    )
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )
    investigation = multiplayer_stage_contract(package, "investigation")
    settlement = investigation.settlement
    assert isinstance(settlement, SecretVoteSettlementDefinition)

    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "stage.confirm_read", "investigation"),
        )
    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "discussion.confirm_close", "investigation"),
        )
    for member in members:
        room = _apply(
            room,
            member,
            SubmitSettlementCommand(
                command_id=uuid4(),
                expected_revision=room.revision,
                type="settlement.submit",
                payload=SubmitSettlementPayload(
                    settlement_id=settlement.settlement_id,
                    option_id="investigator-account",
                ),
            ),
        )

    revealed = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert [material.id for material in revealed.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]

    room = _apply(
        room,
        members[0],
        _stage_command(room, "stage.advance", "investigation"),
    )
    restored = decode_room_game_state(room)
    assert restored.prior_revealed_material_ids == (
        "arrival-photo",
        "witness-note",
    )
    advanced = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert advanced.stage_id == "final-judgment"
    assert [material.id for material in advanced.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]


def test_non_mutating_commands_reject_invalid_stage_material_order() -> None:
    room, members = _active_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )
    state = decode_room_game_state(room)
    invalid_state = GameStateV2.model_validate(
        state.model_copy(
            update={
                "stage": state.stage.model_copy(
                    update={
                        "phase": StagePhase.DISCUSS,
                        "read_member_ids": state.room.required_member_ids,
                        "revealed_material_ids": ("witness-note", "arrival-photo"),
                    }
                )
            }
        ).model_dump()
    )
    invalid_room = replace(room, state=invalid_state.model_dump(mode="json"))
    commands: tuple[MultiplayerCommand, ...] = (
        SendDiscussionMessageCommand(
            command_id=uuid4(),
            expected_revision=room.revision,
            type="discussion.send_message",
            payload=SendDiscussionMessagePayload(
                stage_id="investigation",
                message_id=uuid4(),
                text="顺序异常不应接受消息。",
            ),
        ),
        RoomResyncCommand(
            command_id=uuid4(),
            expected_revision=room.revision,
            type="room.resync",
            payload=RoomResyncPayload(last_event_sequence=0),
        ),
    )

    for command in commands:
        with pytest.raises(ApiError) as exc_info:
            apply_gameplay_command(
                room=invalid_room,
                member=members[0],
                command=command,
                package=package,
            )
        assert exc_info.value.error.code == "ROOM_STATE_INVALID"


def test_snapshot_projects_only_fresh_member_scene_presence() -> None:
    room, members = _active_room()
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    now = datetime.now(UTC)
    fresh = replace(
        members[0],
        scene_x=1455.0,
        scene_y=970.0,
        scene_facing="left",
        scene_moving=True,
        scene_updated_at=now,
    )
    stale = replace(
        members[1],
        scene_x=945.0,
        scene_y=970.0,
        scene_facing="right",
        scene_moving=True,
        scene_updated_at=now - timedelta(seconds=16),
    )

    snapshot = project_gameplay_snapshot(
        room=room,
        member=fresh,
        members=(fresh, stale),
        presence_now=now,
        package=package,
        event_rows=(),
    )

    first, second = snapshot.players
    assert first.scene_online is True
    assert (first.scene_x, first.scene_y, first.scene_facing, first.scene_moving) == (
        1455.0,
        970.0,
        "left",
        True,
    )
    assert second.scene_online is False
    assert (second.scene_x, second.scene_y, second.scene_facing) == (None, None, None)
    assert second.scene_moving is False
    serialized = snapshot.model_dump_json()
    assert "scene_updated_at" not in serialized
    assert "principal_id" not in serialized


@pytest.mark.parametrize(
    ("final_option_id", "expected_ending_id", "expected_outcome_text"),
    (
        (
            "timeline-conflict",
            "conflicting-accounts",
            "你们确认知情人未经登记进入并隐瞒事实，同时拒绝把备用钥匙和金属声夸大成破门或损毁记录的证据。",
        ),
        (
            "records-insufficient",
            "insufficient-evidence",
            "你们作出了破门并损毁记录的重指控；完整时间线随后表明，门锁始终完好，金属声来自掉落的钥匙。",
        ),
    ),
)
def test_real_gameplay_commands_use_frozen_package_for_both_endings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    final_option_id: str,
    expected_ending_id: str,
    expected_outcome_text: str,
) -> None:
    source_root = tmp_path / "mp1-two-player"
    shutil.copytree(PACKAGE_ROOT, source_root)
    monkeypatch.setattr(
        "engine.tests.test_multiplayer_gameplay_service.PACKAGE_ROOT",
        source_root,
    )
    room, members = _active_room()
    package = decode_runtime_package_snapshot(
        room.runtime_package_snapshot,
        room.runtime_package_sha256,
    )

    final_path = source_root / "stages" / "final-judgment.yml"
    final_path.write_text(
        final_path.read_text(encoding="utf-8").replace(
            '    conflicting-accounts: "conflicting-accounts"\n'
            '    insufficient-evidence: "insufficient-evidence"',
            '    conflicting-accounts: "insufficient-evidence"\n'
            '    insufficient-evidence: "conflicting-accounts"',
        ),
        encoding="utf-8",
    )
    endings_path = source_root / "endings.yml"
    endings_path.write_text(
        endings_path.read_text(encoding="utf-8").replace(
            "你们确认知情人未经登记进入并隐瞒事实",
            "源目录已经改写，不应进入冻结房间",
        ),
        encoding="utf-8",
    )
    truth_path = source_root / "dm_guide" / "truth.yml"
    truth_path.write_text(
        truth_path.read_text(encoding="utf-8").replace(
            "知情人于二十点零五分违规使用备用钥匙",
            "源目录已经改写，不应进入冻结复盘",
        ),
        encoding="utf-8",
    )
    mutated_package = load_package_directory(source_root, publish=True)
    mutated_final = multiplayer_stage_contract(mutated_package, "final-judgment")
    mutated_settlement = mutated_final.settlement
    assert isinstance(mutated_settlement, FinalJudgmentSettlementDefinition)
    assert mutated_settlement.ending_by_outcome == {
        "conflicting-accounts": "insufficient-evidence",
        "insufficient-evidence": "conflicting-accounts",
    }
    assert "源目录已经改写，不应进入冻结房间" in str(mutated_package.endings)
    assert "源目录已经改写，不应进入冻结复盘" in str(mutated_package.dm_guide)

    investigation = multiplayer_stage_contract(package, "investigation")
    investigation_settlement = investigation.settlement
    assert isinstance(investigation_settlement, SecretVoteSettlementDefinition)

    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "stage.confirm_read", "investigation"),
        )
    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "discussion.confirm_close", "investigation"),
        )
    for member in members:
        room = _apply(
            room,
            member,
            SubmitSettlementCommand(
                command_id=uuid4(),
                expected_revision=room.revision,
                type="settlement.submit",
                payload=SubmitSettlementPayload(
                    settlement_id=investigation_settlement.settlement_id,
                    option_id="investigator-account",
                ),
            ),
        )

    revealed = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert revealed.phase == "reveal"
    assert revealed.can_advance is True
    assert revealed.settlement is not None
    assert revealed.settlement.revealed is True
    assert revealed.settlement.outcome_id == "trust-investigator"
    option_text = next(
        option.text for option in revealed.settlement.options if option.id == "investigator-account"
    )
    assert option_text == "金属声本身不能证明破门，来源可能是值班室内已有的人或物"
    assert "强行进入" not in option_text
    assert "无人从走廊进入" not in option_text
    assert {ballot.option_id for ballot in revealed.settlement.revealed_ballots} == {
        "investigator-account"
    }

    room = _apply(
        room,
        members[0],
        _stage_command(room, "stage.advance", "investigation"),
    )
    final_snapshot = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert final_snapshot.stage_id == "final-judgment"
    assert [material.id for material in final_snapshot.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]
    assert [chapter.id for chapter in final_snapshot.chapters] == [
        "investigator-investigation",
        "investigator-final-judgment",
    ]
    assert [material.id for material in final_snapshot.public_materials] == [
        "arrival-photo",
        "witness-note",
    ]

    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "stage.confirm_read", "final-judgment"),
        )
    for member in members:
        room = _apply(
            room,
            member,
            _stage_command(room, "discussion.confirm_close", "final-judgment"),
        )
    final_definition = multiplayer_stage_contract(package, "final-judgment")
    final_settlement = final_definition.settlement
    assert isinstance(final_settlement, FinalJudgmentSettlementDefinition)
    for member in members:
        room = _apply(
            room,
            member,
            ConfirmSharedChoiceCommand(
                command_id=uuid4(),
                expected_revision=room.revision,
                type="settlement.confirm_shared_choice",
                payload=ConfirmSharedChoicePayload(
                    settlement_id=final_settlement.settlement_id,
                    option_id=final_option_id,
                ),
            ),
        )

    completed = project_gameplay_snapshot(
        room=room,
        member=members[0],
        package=package,
        event_rows=(),
    )
    assert room.status == "completed"
    assert completed.status == "completed"
    assert completed.ending_id == expected_ending_id
    assert completed.settlement is not None
    assert completed.settlement.outcome_id == expected_ending_id
    assert [material.id for material in completed.public_materials] == [
        "arrival-photo",
        "witness-note",
        "case-reconstruction",
        (
            "limited-finding"
            if expected_ending_id == "conflicting-accounts"
            else "unsupported-finding"
        ),
    ]
    assert completed.can_advance is False

    reviews = tuple(
        project_multiplayer_review(
            room=room,
            member=member,
            package=package,
        )
        for member in members
    )
    assert {review.member_id for review in reviews} == {str(member.id) for member in members}
    assert all(review.ending.id == expected_ending_id for review in reviews)
    assert all(review.ending.outcome_text == expected_outcome_text for review in reviews)
    assert all(
        review.truth.case_summary is not None
        and review.truth.case_summary.startswith("知情人于二十点零五分违规使用备用钥匙")
        for review in reviews
    )
    assert {chapter.character_id for chapter in reviews[0].chapters} == {
        "investigator",
        "insider",
    }
    assert reviews[0].final_settlement.reveal == "outcome_only"
    review_json = reviews[0].model_dump_json()
    assert "private_by_member" not in review_json
    assert "ballots" not in review_json


def test_room_state_decoder_preserves_v2_prior_material_field() -> None:
    room, _members = _active_room()
    transitional_state = {
        **room.state,
        "prior_revealed_material_ids": ["arrival-photo"],
    }

    restored = decode_room_game_state(replace(room, state=transitional_state))

    assert restored.room_revision == room.revision
    assert restored.prior_revealed_material_ids == ("arrival-photo",)


def test_room_state_decoder_rejects_relational_mismatch() -> None:
    room, _members = _active_room()
    assert decode_room_game_state(room).room_revision == room.revision

    for invalid in (
        replace(room, revision=room.revision + 1),
        replace(room, status="completed"),
        replace(room, state_schema_version=1),
    ):
        with pytest.raises(ApiError) as exc_info:
            decode_room_game_state(invalid)
        assert exc_info.value.error.code == "ROOM_STATE_INVALID"
