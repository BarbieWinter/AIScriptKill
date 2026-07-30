"""验证 Multiplayer v1 状态、命令、事件、快照和 WebSocket 契约。"""

import json
from typing import cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from engine.contracts.multiplayer_v1.base import ContractModel
from engine.contracts.multiplayer_v1.commands import (
    COMMAND_ADAPTER,
    AssignCharacterCommand,
    CommandResultData,
    CommandResultV1,
)
from engine.contracts.multiplayer_v1.errors import CommandError, MultiplayerErrorCode
from engine.contracts.multiplayer_v1.events import (
    EVENT_ADAPTER,
    ChapterGrantedEvent,
    EventAudience,
    RoomStatusChangedEvent,
)
from engine.contracts.multiplayer_v1.snapshots import (
    ParticipantSnapshotV1,
    build_participant_snapshot,
)
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    PrivateSettlementSubmission,
    RoomState,
    SettlementRuntimeState,
    StageRuntimeState,
    decode_game_state_v2,
    encode_game_state_v2,
)
from engine.contracts.multiplayer_v1.vocabulary import (
    AudienceScope,
    CharacterAssignmentPolicy,
    CommandStatus,
    DiscussionClosePolicy,
    FinalAnswerMode,
    RoomStatus,
    SettlementEffect,
    SettlementMode,
    SettlementReveal,
    StagePhase,
    StartPolicy,
    SubmissionChangePolicy,
)
from engine.contracts.multiplayer_v1.websocket import (
    CLIENT_FRAME_ADAPTER,
    SERVER_FRAME_ADAPTER,
    WS_PROTOCOL_VERSION,
    RoomEventFrame,
)
from engine.core.checkpoint_codec import ENCODING_VERSION

SESSION_ID = UUID("12345678-1234-5678-1234-567812345678")
COMMAND_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
EVENT_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
MESSAGE_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")


class _ExampleContract(ContractModel):
    enabled: bool


def _game_state() -> GameStateV2:
    return GameStateV2(
        state_schema_version=GAME_STATE_SCHEMA_VERSION,
        session_id=SESSION_ID,
        room_revision=7,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=("member-a", "member-b"),
            current_stage_id="stage-1",
        ),
        players={
            "member-a": PlayerState(
                member_id="member-a",
                character_id="character-a",
                ready=True,
            ),
            "member-b": PlayerState(
                member_id="member-b",
                character_id="character-b",
                ready=True,
            ),
        },
        private_by_member={
            "member-a": PrivatePlayerState(
                character_id="character-a",
                unlocked_chapter_ids=("chapter-a-secret",),
                settlement_submission=PrivateSettlementSubmission(
                    settlement_id="vote-1",
                    option_id="option-a-secret",
                ),
            ),
            "member-b": PrivatePlayerState(
                character_id="character-b",
                unlocked_chapter_ids=("chapter-b-secret",),
                settlement_submission=PrivateSettlementSubmission(
                    settlement_id="vote-1",
                    option_id="option-b-secret",
                ),
            ),
        },
        stage=StageRuntimeState(
            stage_id="stage-1",
            phase=StagePhase.SETTLE,
            read_member_ids=("member-a", "member-b"),
            discussion_close_member_ids=("member-a",),
            settlement=SettlementRuntimeState(
                settlement_id="vote-1",
                mode=SettlementMode.SECRET_VOTE,
                required_member_ids=("member-a", "member-b"),
                submitted_member_ids=("member-a",),
                outcome_id=None,
                revealed=False,
            ),
            revealed_material_ids=("public-clue",),
        ),
    )


def _state_json_mapping() -> dict[str, object]:
    raw = json.loads(_game_state().model_dump_json())
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


def _room_status_event_json() -> str:
    return json.dumps(
        {
            "event_id": str(EVENT_ID),
            "session_id": str(SESSION_ID),
            "sequence": 8,
            "revision": 7,
            "audience": {"scope": "room"},
            "type": "room.status_changed",
            "status": "active",
        }
    )


def test_contract_model_is_strict_frozen_and_rejects_unknown_fields() -> None:
    # 给定：一个只声明布尔字段的多人契约。
    contract = _ExampleContract(enabled=True)

    # 当/则：契约拒绝类型强制转换、未知字段和构造后的赋值。
    with pytest.raises(ValidationError):
        _ExampleContract.model_validate({"enabled": 1})
    with pytest.raises(ValidationError):
        _ExampleContract.model_validate({"enabled": True, "future": "field"})
    with pytest.raises(ValidationError):
        contract.enabled = False


def test_completed_state_requires_revealed_outcome_and_authored_ending() -> None:
    state = _game_state()
    revealed_settlement = state.stage.settlement
    assert revealed_settlement is not None
    revealed_settlement = revealed_settlement.model_copy(
        update={
            "submitted_member_ids": ("member-a", "member-b"),
            "revealed": True,
            "outcome_id": "ending-a",
        }
    )
    completed_shape = state.model_copy(
        update={
            "room": state.room.model_copy(update={"status": RoomStatus.COMPLETED}),
            "stage": state.stage.model_copy(
                update={
                    "phase": StagePhase.REVEAL,
                    "settlement": revealed_settlement,
                }
            ),
        }
    )

    with pytest.raises(ValidationError, match="requires ending_id"):
        GameStateV2.model_validate(completed_shape.model_dump())

    completed = GameStateV2.model_validate(
        completed_shape.model_copy(update={"ending_id": "ending-b"}).model_dump()
    )
    assert completed.room.status is RoomStatus.COMPLETED
    assert completed.stage.settlement is not None
    assert completed.stage.settlement.outcome_id == "ending-a"
    assert completed.ending_id == "ending-b"

    missing_outcome = completed_shape.model_copy(
        update={
            "ending_id": "ending-b",
            "stage": completed_shape.stage.model_copy(
                update={"settlement": revealed_settlement.model_copy(update={"outcome_id": None})}
            ),
        }
    )
    with pytest.raises(ValidationError, match="revealed settlement requires outcome_id"):
        GameStateV2.model_validate(missing_outcome.model_dump())

    active = state.model_copy(update={"ending_id": "ending-a"})
    with pytest.raises(ValidationError, match="only a completed room"):
        GameStateV2.model_validate(active.model_dump())


def test_vocabulary_and_error_codes_are_stable() -> None:
    assert [value.value for value in RoomStatus] == ["lobby", "active", "completed", "closed"]
    assert [value.value for value in StagePhase] == ["read", "discuss", "settle", "reveal"]
    assert [value.value for value in SettlementMode] == [
        "none",
        "secret_vote",
        "shared_choice",
        "final_judgment",
    ]
    assert [value.value for value in CommandStatus] == ["accepted", "rejected"]
    assert [value.value for value in AudienceScope] == ["room", "member"]
    assert [value.value for value in SettlementReveal] == [
        "named_ballots",
        "aggregate",
        "outcome_only",
    ]
    assert [value.value for value in SubmissionChangePolicy] == [
        "forbidden",
        "allowed_before_complete",
    ]
    assert [value.value for value in SettlementEffect] == ["record_and_continue", "branch"]
    assert [value.value for value in CharacterAssignmentPolicy] == ["required"]
    assert [value.value for value in DiscussionClosePolicy] == ["all_players"]
    assert [value.value for value in FinalAnswerMode] == ["shared_choice", "individual_secret"]
    assert [value.value for value in StartPolicy] == ["all_players_ready"]
    assert [value.value for value in MultiplayerErrorCode] == [
        "AUTH_REQUIRED",
        "NOT_ROOM_MEMBER",
        "PRIVATE_CONTENT_FORBIDDEN",
        "REVISION_MISMATCH",
        "COMMAND_ID_REUSED",
        "PHASE_MISMATCH",
        "SETTLEMENT_ALREADY_SUBMITTED",
        "INVALID_COMMAND",
        "COMMAND_NOT_AVAILABLE",
        "ROOM_NOT_IN_LOBBY",
        "ROOM_NOT_ACTIVE",
        "ROOM_CLOSED",
        "ROOM_ALREADY_COMPLETED",
        "HOST_REQUIRED",
        "CHARACTER_NOT_PLAYABLE",
        "CHARACTER_ALREADY_ASSIGNED",
        "CHARACTER_REQUIRED",
        "ROOM_NOT_FULL",
        "ASSIGNMENTS_INCOMPLETE",
        "PLAYERS_NOT_READY",
        "UNSUPPORTED_PROTOCOL_VERSION",
        "FEATURE_DISABLED",
    ]


def test_game_state_v2_round_trips_without_sharing_checkpoint_version() -> None:
    # 给定：包含公开进度和按成员隔离私有状态的规范 V2 状态。
    state = _game_state()

    # 当：状态只通过多人状态 codec 往返。
    encoded = encode_game_state_v2(state)
    restored = decode_game_state_v2(encoded)

    # 则：状态版本保持 2，而 LangGraph 检查点信封继续独立使用版本 1。
    assert restored == state
    assert restored.state_schema_version == GAME_STATE_SCHEMA_VERSION == 2
    assert ENCODING_VERSION == 1
    assert b'"state_schema_version":2' in encoded


@pytest.mark.parametrize(
    "mutation",
    ("duplicate-members", "mapping-key-mismatch", "stage-outsider", "private-outsider"),
)
def test_game_state_rejects_invalid_member_collections(mutation: str) -> None:
    # 给定：一个原本有效的规范状态 JSON。
    raw = _state_json_mapping()

    # 当：成员映射或确认集合破坏结构不变量。
    if mutation == "duplicate-members":
        cast(dict[str, object], raw["room"])["required_member_ids"] = ["member-a", "member-a"]
    elif mutation == "mapping-key-mismatch":
        cast(dict[str, object], raw["players"])["member-a"] = {
            "member_id": "member-b",
            "character_id": "character-a",
            "ready": True,
        }
    elif mutation == "stage-outsider":
        cast(dict[str, object], raw["stage"])["read_member_ids"] = ["member-a", "outsider"]
    else:
        cast(dict[str, object], raw["private_by_member"])["outsider"] = {
            "character_id": None,
            "unlocked_chapter_ids": [],
        }

    # 则：状态边界拒绝不一致输入。
    with pytest.raises(ValidationError):
        GameStateV2.model_validate_json(json.dumps(raw))


def test_game_state_accepts_json_object_key_reordering() -> None:
    raw = _state_json_mapping()
    required_member_ids = cast(dict[str, object], raw["room"])["required_member_ids"]
    assert required_member_ids == ["member-a", "member-b"]
    raw["players"] = dict(reversed(list(cast(dict[str, object], raw["players"]).items())))
    raw["private_by_member"] = dict(
        reversed(list(cast(dict[str, object], raw["private_by_member"]).items()))
    )

    restored = GameStateV2.model_validate_json(json.dumps(raw))

    assert restored.room.required_member_ids == ("member-a", "member-b")
    assert set(restored.players) == {"member-a", "member-b"}
    assert set(restored.private_by_member) == {"member-a", "member-b"}


def test_game_state_rejects_unknown_enum_extra_field_and_wrong_version() -> None:
    raw = _state_json_mapping()
    room = raw["room"]
    assert isinstance(room, dict)

    room["status"] = "paused"
    with pytest.raises(ValidationError):
        GameStateV2.model_validate_json(json.dumps(raw))

    raw = _state_json_mapping()
    raw["future"] = True
    with pytest.raises(ValidationError):
        GameStateV2.model_validate_json(json.dumps(raw))

    raw = _state_json_mapping()
    raw["state_schema_version"] = 1
    with pytest.raises(ValidationError):
        GameStateV2.model_validate_json(json.dumps(raw))

    raw = _state_json_mapping()
    del raw["state_schema_version"]
    with pytest.raises(ValidationError):
        GameStateV2.model_validate_json(json.dumps(raw))
    assert "state_schema_version" in GameStateV2.model_json_schema()["required"]


def test_participant_snapshot_crops_other_members_private_state() -> None:
    # 给定：房间状态含两名成员各自不同的私有章节和投票。
    snapshot = build_participant_snapshot(
        _game_state(),
        member_id="member-a",
        event_head_sequence=8,
    )

    # 当：为 member-a 序列化参与者快照。
    encoded = snapshot.model_dump_json()
    mapping = snapshot.model_dump(mode="json")

    # 则：快照只含当前成员 private_state，不能表达 private_by_member。
    assert mapping["snapshot_version"] == 1
    assert "snapshot_version" in ParticipantSnapshotV1.model_json_schema()["required"]
    assert "private_by_member" not in mapping
    assert mapping["private_state"]["unlocked_chapter_ids"] == ["chapter-a-secret"]
    assert "chapter-b-secret" not in encoded
    assert "option-b-secret" not in encoded

    mapping["private_by_member"] = {}
    with pytest.raises(ValidationError):
        ParticipantSnapshotV1.model_validate_json(json.dumps(mapping))


def test_command_union_accepts_all_frozen_types_and_rejects_future_payloads() -> None:
    payloads = {
        "room.assign_character": {"character_id": "character-a"},
        "room.unassign_character": {},
        "room.ready": {"ready": True},
        "room.start": {},
        "room.end_incomplete": {"reason": "host ended room"},
        "stage.confirm_read": {"stage_id": "stage-1"},
        "stage.advance": {"stage_id": "stage-1"},
        "discussion.send_message": {
            "stage_id": "stage-1",
            "message_id": str(MESSAGE_ID),
            "text": "我发现了新的矛盾。",
        },
        "discussion.confirm_close": {"stage_id": "stage-1"},
        "discussion.revoke_close": {"stage_id": "stage-1"},
        "settlement.submit": {"settlement_id": "vote-1", "option_id": "option-a"},
        "settlement.confirm_shared_choice": {
            "settlement_id": "choice-1",
            "option_id": "option-a",
        },
        "hint.request": {"hint_id": "motive-chain", "level": 1},
        "hint.confirm": {"hint_id": "motive-chain", "level": 1},
        "room.resync": {"last_event_sequence": 8},
    }

    commands = [
        COMMAND_ADAPTER.validate_json(
            json.dumps(
                {
                    "command_id": str(COMMAND_ID),
                    "expected_revision": 7,
                    "type": command_type,
                    "payload": payload,
                }
            )
        )
        for command_type, payload in payloads.items()
    ]

    assert len(commands) == 15
    assert isinstance(commands[0], AssignCharacterCommand)
    assert COMMAND_ADAPTER.json_schema()["discriminator"]["propertyName"] == "type"

    for unsupported_type in ("stage.revoke_read", "room.future_command"):
        with pytest.raises(ValidationError):
            COMMAND_ADAPTER.validate_json(
                json.dumps(
                    {
                        "command_id": str(COMMAND_ID),
                        "expected_revision": 7,
                        "type": unsupported_type,
                        "payload": {"stage_id": "stage-1"},
                    }
                )
            )
    with pytest.raises(ValidationError):
        COMMAND_ADAPTER.validate_json(
            json.dumps(
                {
                    "command_id": str(COMMAND_ID),
                    "expected_revision": 7,
                    "type": "room.assign_character",
                    "payload": {"character_id": "character-a", "admin": True},
                }
            )
        )

    for command_type, payload in (
        ("hint.request", {"hint_id": "motive-chain", "level": 0}),
        ("hint.confirm", {"hint_id": "motive-chain", "level": 4}),
        ("room.resync", {"last_event_sequence": -1}),
        ("hint.request", {"hint_id": "", "level": 1}),
        ("room.resync", {"last_event_sequence": 8, "member_id": "member-a"}),
        ("room.end_incomplete", {"reason": "x" * 2001}),
    ):
        with pytest.raises(ValidationError):
            COMMAND_ADAPTER.validate_json(
                json.dumps(
                    {
                        "command_id": str(COMMAND_ID),
                        "expected_revision": 7,
                        "type": command_type,
                        "payload": payload,
                    }
                )
            )


def test_command_result_enforces_accepted_and_rejected_shapes() -> None:
    accepted = CommandResultV1(
        command_id=COMMAND_ID,
        status=CommandStatus.ACCEPTED,
        revision=8,
        event_sequence=9,
        result=CommandResultData(event_ids=(EVENT_ID,)),
        replayed=False,
    )
    rejected = CommandResultV1(
        command_id=COMMAND_ID,
        status=CommandStatus.REJECTED,
        revision=8,
        event_sequence=9,
        error=CommandError(
            code=MultiplayerErrorCode.REVISION_MISMATCH,
            message="revision mismatch",
        ),
        replayed=True,
    )

    assert accepted.error is None
    assert rejected.result is None
    with pytest.raises(ValidationError):
        CommandResultV1(
            command_id=COMMAND_ID,
            status=CommandStatus.ACCEPTED,
            revision=8,
            event_sequence=9,
        )


def test_event_audience_and_union_protect_member_only_chapters() -> None:
    room_event = EVENT_ADAPTER.validate_json(_room_status_event_json())
    assert isinstance(room_event, RoomStatusChangedEvent)
    assert EVENT_ADAPTER.json_schema()["discriminator"]["propertyName"] == "type"

    member_audience = EventAudience(scope=AudienceScope.MEMBER, member_id="member-a")
    chapter_event = ChapterGrantedEvent(
        event_id=EVENT_ID,
        session_id=SESSION_ID,
        sequence=9,
        revision=8,
        audience=member_audience,
        type="chapter.granted",
        member_id="member-a",
        character_id="character-a",
        chapter_id="secret-chapter",
    )
    assert chapter_event.audience.member_id == "member-a"

    with pytest.raises(ValidationError):
        EventAudience(scope=AudienceScope.MEMBER)
    with pytest.raises(ValidationError):
        EventAudience(scope=AudienceScope.ROOM, member_id="member-a")
    with pytest.raises(ValidationError):
        ChapterGrantedEvent(
            event_id=EVENT_ID,
            session_id=SESSION_ID,
            sequence=9,
            revision=8,
            audience=EventAudience(scope=AudienceScope.ROOM),
            type="chapter.granted",
            member_id="member-a",
            character_id="character-a",
            chapter_id="secret-chapter",
        )
    with pytest.raises(ValidationError):
        EVENT_ADAPTER.validate_json(
            _room_status_event_json().replace("room.status_changed", "dm.note")
        )


def test_websocket_frames_keep_protocol_version_identity_boundary_and_direction() -> None:
    ping = CLIENT_FRAME_ADAPTER.validate_json('{"type":"session.ping"}')
    hello = CLIENT_FRAME_ADAPTER.validate_json(
        '{"type":"connection.hello","data":'
        '{"protocol_version":1,"ticket":"opaque-ticket","last_event_sequence":8}}'
    )
    ready = SERVER_FRAME_ADAPTER.validate_json(
        json.dumps(
            {
                "type": "connection.ready",
                "data": {
                    "protocol_version": 1,
                    "session_id": str(SESSION_ID),
                    "member_id": "member-a",
                    "revision": 7,
                    "event_head_sequence": 8,
                },
            }
        )
    )
    event_frame = SERVER_FRAME_ADAPTER.validate_json(
        json.dumps({"type": "room.event", "data": {"event": json.loads(_room_status_event_json())}})
    )

    assert ping.type == "session.ping"
    assert hello.type == "connection.hello"
    assert hello.data.protocol_version == WS_PROTOCOL_VERSION == 1
    assert ready.type == "connection.ready"
    assert ready.data.protocol_version == WS_PROTOCOL_VERSION == 1
    assert ready.data.member_id == "member-a"
    assert isinstance(event_frame, RoomEventFrame)
    assert SERVER_FRAME_ADAPTER.json_schema()["discriminator"]["propertyName"] == "type"

    with pytest.raises(ValidationError):
        CLIENT_FRAME_ADAPTER.validate_json(
            '{"type":"connection.hello","data":{"protocol_version":2,"ticket":"ticket"}}'
        )
    with pytest.raises(ValidationError):
        CLIENT_FRAME_ADAPTER.validate_json(
            '{"type":"connection.hello","data":{"protocol_version":1,"ticket":""}}'
        )
    with pytest.raises(ValidationError):
        CLIENT_FRAME_ADAPTER.validate_json(
            '{"type":"connection.hello","data":'
            '{"protocol_version":1,"ticket":"ticket","last_event_sequence":-1}}'
        )
    with pytest.raises(ValidationError):
        CLIENT_FRAME_ADAPTER.validate_json(
            json.dumps(
                {
                    "type": "connection.hello",
                    "data": {
                        "protocol_version": 1,
                        "ticket": "ticket",
                        "session_id": str(SESSION_ID),
                        "member_id": "member-a",
                        "revision": 7,
                        "event_head_sequence": 8,
                    },
                }
            )
        )
    with pytest.raises(ValidationError):
        CLIENT_FRAME_ADAPTER.validate_json(
            json.dumps(
                {
                    "type": "connection.ready",
                    "data": {
                        "protocol_version": 1,
                        "session_id": str(SESSION_ID),
                        "member_id": "member-a",
                        "revision": 7,
                        "event_head_sequence": 8,
                    },
                }
            )
        )
    with pytest.raises(ValidationError):
        SERVER_FRAME_ADAPTER.validate_json(
            '{"type":"connection.hello","data":{"protocol_version":1,"ticket":"ticket"}}'
        )
    with pytest.raises(ValidationError):
        SERVER_FRAME_ADAPTER.validate_json('{"type":"room.future","data":{}}')
