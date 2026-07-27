from __future__ import annotations

import ast
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_type_hints
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from engine.api.errors import ApiError
from engine.api.middleware.auth import VerifiedAnonymousPrincipal
from engine.api.routes import sessions
from engine.api.schemas.multiplayer_rooms import (
    CreateMultiplayerSessionRequest,
    UpdateScenePresenceRequest,
)
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    AssignCharacterPayload,
    ConfirmReadCommand,
    MultiplayerCommand,
    StageCommandPayload,
)
from engine.contracts.multiplayer_v1.state import (
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus
from engine.core.package_loader import load_package_directory
from engine.core.runtime_package_snapshot import encode_runtime_package_snapshot
from engine.repositories.multiplayer_room_models import (
    RoomMutationContext,
    StoredMultiplayerRoom,
    StoredRoomAssignment,
    StoredRoomMember,
)
from engine.services import multiplayer_feature
from engine.services import multiplayer_room_service as service

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"


class _CommitDb:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def commit(self) -> None:
        self.commit_calls += 1


class _CreateRepository:
    def __init__(self) -> None:
        self.lock_calls = 0
        self.create_calls = 0

    async def advisory_lock(self, _session_id):
        self.lock_calls += 1

    async def create_room(self, **_kwargs):
        self.create_calls += 1
        raise AssertionError("invalid package must be rejected before room creation")


class _PresenceRepository:
    def __init__(self, room: StoredMultiplayerRoom, member: StoredRoomMember | None) -> None:
        self.room = room
        self.member = member
        self.updated: dict[str, object] | None = None

    async def advisory_lock(self, _session_id):
        return None

    async def lock_room(self, _session_id):
        return self.room

    async def get_room(self, _session_id):
        return self.room

    async def joined_member(self, _session_id, _principal_id):
        return self.member

    async def update_scene_presence(self, **kwargs):
        self.updated = kwargs
        return self.member


class _NoOpAssignmentRepository:
    def __init__(
        self,
        room: StoredMultiplayerRoom,
        member: StoredRoomMember,
        assignment: StoredRoomAssignment,
    ) -> None:
        self.room = room
        self.member = member
        self.assignment = assignment
        self.write_calls = 0

    async def advisory_lock(self, _session_id):
        return None

    async def lock_room(self, _session_id):
        return self.room

    async def joined_member(self, _session_id, _principal_id):
        return self.member

    async def assignment_for_member(self, _session_id, _member_id):
        return self.assignment

    async def assignment_for_character(self, _session_id, _character_id):
        raise AssertionError("same-character no-op must not check another holder")

    async def set_assignment(self, **_kwargs):
        self.write_calls += 1

    async def increment_revision(self, _session_id):
        self.write_calls += 1
        return self.room.revision + 1


class _StartRepository:
    def __init__(
        self,
        members: tuple[StoredRoomMember, ...],
        assignments: tuple[StoredRoomAssignment, ...],
    ) -> None:
        self.members = members
        self.assignment_rows = assignments
        self.required = None
        self.state = None
        self.revision = None
        self.revoked = False

    async def joined_members(self, _session_id):
        return self.members

    async def assignments(self, _session_id):
        return self.assignment_rows

    async def add_required_members(self, _session_id, required):
        self.required = tuple(required)

    async def activate_room(self, *, session_id, state, revision):
        del session_id
        self.state = state
        self.revision = revision

    async def revoke_all_invites(self, _session_id):
        self.revoked = True


def _room(*, revision: int = 7) -> StoredMultiplayerRoom:
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    snapshot = encode_runtime_package_snapshot(package)
    now = datetime.now(UTC)
    return StoredMultiplayerRoom(
        id=uuid4(),
        script_id=package.package.id,
        status="lobby",
        revision=revision,
        event_head_sequence=0,
        state_schema_version=2,
        state={},
        runtime_package_version=package.package.version,
        runtime_package_snapshot=dict(snapshot.payload),
        runtime_package_sha256=snapshot.sha256,
        created_at=now,
        started_at=None,
        closed_at=None,
    )


def _package_with_missing_ending_mapping():
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    final_stage = package.stages[-1]
    definition = dict(final_stage.definition)
    settlement = dict(definition["settlement"])
    ending_by_outcome = dict(settlement["ending_by_outcome"])
    ending_by_outcome.pop("insufficient-evidence")
    settlement["ending_by_outcome"] = ending_by_outcome
    definition["settlement"] = settlement
    return replace(
        package,
        stages=(*package.stages[:-1], replace(final_stage, definition=definition)),
    )


def _room_with_missing_ending_mapping() -> StoredMultiplayerRoom:
    room = _room()
    snapshot = encode_runtime_package_snapshot(_package_with_missing_ending_mapping())
    return replace(
        room,
        runtime_package_snapshot=dict(snapshot.payload),
        runtime_package_sha256=snapshot.sha256,
    )


def _member(
    room: StoredMultiplayerRoom,
    *,
    role: str,
    joined_at: datetime,
) -> StoredRoomMember:
    return StoredRoomMember(
        id=uuid4(),
        session_id=room.id,
        principal_id=uuid4(),
        room_role=role,  # type: ignore[arg-type]
        ready_at=joined_at,
        joined_at=joined_at,
    )


def test_repository_source_contains_no_commit_call() -> None:
    repository_path = (
        Path(__file__).resolve().parents[1] / "repositories" / "multiplayer_room_repository.py"
    )
    tree = ast.parse(repository_path.read_text(encoding="utf-8"))

    commit_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "commit"
    ]

    assert commit_calls == []


def test_current_route_precedes_dynamic_session_route() -> None:
    paths = [route.path for route in sessions.router.routes]
    assert paths.index("/sessions/current") < paths.index("/sessions/{session_id}")


def test_command_route_parses_the_complete_multiplayer_union() -> None:
    annotation = get_type_hints(sessions.post_room_command, include_extras=True)["command"]
    assert annotation == MultiplayerCommand
    parsed = TypeAdapter(annotation).validate_python(
        {
            "command_id": str(uuid4()),
            "expected_revision": 0,
            "type": "stage.confirm_read",
            "payload": {"stage_id": "investigation"},
        }
    )
    assert isinstance(parsed, ConfirmReadCommand)


@pytest.mark.asyncio
async def test_feature_disabled_read_fails_before_repository_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        multiplayer_feature,
        "get_settings",
        lambda: type("Settings", (), {"multiplayer_v1": False})(),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.get_current_multiplayer_session(
            VerifiedAnonymousPrincipal(id=uuid4()),
            object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.error.code == "MULTIPLAYER_DISABLED"


@pytest.mark.asyncio
async def test_unsupported_but_valid_full_command_returns_stable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(service, "require_multiplayer_enabled", lambda: None)
    command = ConfirmReadCommand(
        command_id=uuid4(),
        expected_revision=0,
        type="stage.confirm_read",
        payload=StageCommandPayload(stage_id="investigation"),
    )

    with pytest.raises(ApiError) as exc_info:
        await service.execute_lobby_command(
            str(uuid4()),
            command,
            VerifiedAnonymousPrincipal(id=uuid4()),
            object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.error.code == "COMMAND_NOT_AVAILABLE"


def _active_room_with_member() -> tuple[StoredMultiplayerRoom, StoredRoomMember]:
    lobby = _room()
    now = datetime.now(UTC)
    member = _member(lobby, role="host", joined_at=now)
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    definition = service._stage_definition(  # noqa: SLF001
        "investigation",
        next(stage.definition for stage in package.stages if stage.id == "investigation"),
    )
    member_id = str(member.id)
    state = GameStateV2(
        state_schema_version=2,
        session_id=lobby.id,
        room_revision=lobby.revision,
        room=RoomState(
            status=RoomStatus.ACTIVE,
            required_member_ids=(member_id,),
            current_stage_id=definition.id,
        ),
        players={
            member_id: PlayerState(
                member_id=member_id,
                character_id="investigator",
                ready=True,
            )
        },
        private_by_member={
            member_id: PrivatePlayerState(
                character_id="investigator",
                unlocked_chapter_ids=(definition.chapters["investigator"],),
            )
        },
        stage=service.initialize_stage_runtime(definition, required_member_ids=(member_id,)),
    )
    return replace(lobby, status="active", state=state.model_dump(mode="json")), member


@pytest.mark.asyncio
async def test_scene_presence_derives_member_and_never_advances_room_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room, member = _active_room_with_member()
    repository = _PresenceRepository(room, member)
    db = _CommitDb()
    monkeypatch.setattr(service, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(service, "MultiplayerRoomRepository", lambda _db: repository)

    await service.update_scene_presence(
        str(room.id),
        UpdateScenePresenceRequest(x=1455, y=970, facing="left", moving=True),
        VerifiedAnonymousPrincipal(id=member.principal_id),
        db,  # type: ignore[arg-type]
    )

    assert repository.updated == {
        "session_id": room.id,
        "principal_id": member.principal_id,
        "x": 1455.0,
        "y": 970.0,
        "facing": "left",
        "moving": True,
    }
    assert "member_id" not in repository.updated
    assert db.commit_calls == 1


@pytest.mark.asyncio
async def test_scene_presence_rejects_nonmember_before_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room, _member_row = _active_room_with_member()
    repository = _PresenceRepository(room, None)
    db = _CommitDb()
    monkeypatch.setattr(service, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(service, "MultiplayerRoomRepository", lambda _db: repository)

    with pytest.raises(ApiError) as exc_info:
        await service.update_scene_presence(
            str(room.id),
            UpdateScenePresenceRequest(x=1200, y=970, facing="right"),
            VerifiedAnonymousPrincipal(id=uuid4()),
            db,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.error.code == "NOT_ROOM_MEMBER"
    assert repository.updated is None
    assert db.commit_calls == 0


@pytest.mark.asyncio
async def test_same_assignment_is_noop_but_service_commits_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    room = _room()
    now = datetime.now(UTC)
    member = _member(room, role="host", joined_at=now)
    assignment = StoredRoomAssignment(
        session_id=room.id,
        member_id=member.id,
        character_id="investigator",
        assigned_at=now,
    )
    repository = _NoOpAssignmentRepository(room, member, assignment)
    db = _CommitDb()
    monkeypatch.setattr(service, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(service, "MultiplayerRoomRepository", lambda _db: repository)
    receipt_repository = type(
        "ReceiptRepository",
        (),
        {
            "get_receipt": AsyncMock(return_value=None),
            "get_command_identity": AsyncMock(return_value=None),
            "get_active_processing_receipt": AsyncMock(return_value=None),
            "claim_receipt": AsyncMock(return_value=type("Claimed", (), {"attempt_count": 1})()),
            "finalize_success": AsyncMock(return_value=True),
            "expire_lease": AsyncMock(return_value=True),
        },
    )()
    monkeypatch.setattr(service, "SessionCommandRepository", lambda _db: receipt_repository)
    command = AssignCharacterCommand(
        command_id=uuid4(),
        expected_revision=room.revision,
        type="room.assign_character",
        payload=AssignCharacterPayload(character_id="investigator"),
    )

    result = await service.execute_lobby_command(
        str(room.id),
        command,
        VerifiedAnonymousPrincipal(id=member.principal_id),
        db,  # type: ignore[arg-type]
    )

    assert result.revision == room.revision
    assert result.event_sequence == 0
    assert result.replayed is False
    assert repository.write_calls == 0
    assert db.commit_calls == 2


@pytest.mark.asyncio
async def test_create_rejects_package_before_room_mutation_with_playability_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = _CreateRepository()
    package = _package_with_missing_ending_mapping()
    monkeypatch.setattr(service, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(service, "MultiplayerRoomRepository", lambda _db: repository)
    monkeypatch.setattr(service, "get_runtime_package", AsyncMock(return_value=package))

    with pytest.raises(ApiError) as exc_info:
        await service.create_multiplayer_session(
            CreateMultiplayerSessionRequest(
                mode="multiplayer_v1",
                script_id=package.package.id,
            ),
            VerifiedAnonymousPrincipal(id=uuid4()),
            object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.error.code == "PACKAGE_NOT_MULTIPLAYER"
    assert exc_info.value.error.details["diagnostic_code"] == (
        "PACKAGE_MULTIPLAYER_ENDING_MAPPING_MISSING"
    )
    assert exc_info.value.error.details["stage_id"] == "final-judgment"
    assert exc_info.value.error.details["outcome_id"] == "insufficient-evidence"
    assert repository.lock_calls == 1
    assert repository.create_calls == 0


@pytest.mark.asyncio
async def test_start_rejects_frozen_package_with_same_playability_diagnostic() -> None:
    room = _room_with_missing_ending_mapping()
    now = datetime.now(UTC)
    host = _member(room, role="host", joined_at=now)
    guest = _member(room, role="player", joined_at=now + timedelta(milliseconds=1))
    repository = _StartRepository((host, guest), ())

    with pytest.raises(ApiError) as exc_info:
        await service._start_room(  # noqa: SLF001
            repository,  # type: ignore[arg-type]
            RoomMutationContext(room=room, member=host),
        )

    assert exc_info.value.error.code == "ROOM_PACKAGE_INVALID"
    assert exc_info.value.error.message == ("最终判断结果缺少结局映射: insufficient-evidence")
    assert exc_info.value.error.details == {
        "diagnostic_code": "PACKAGE_MULTIPLAYER_ENDING_MAPPING_MISSING",
        "field": ("stages.final-judgment.settlement.ending_by_outcome.insufficient-evidence"),
        "stage_id": "final-judgment",
        "outcome_id": "insufficient-evidence",
        "ending_id": None,
    }
    assert repository.required is None
    assert repository.state is None
    assert repository.revoked is False


@pytest.mark.asyncio
async def test_start_builds_canonical_private_state_and_atomic_writes() -> None:
    room = _room(revision=11)
    now = datetime.now(UTC)
    host = _member(room, role="host", joined_at=now)
    guest = _member(room, role="player", joined_at=now + timedelta(milliseconds=1))
    assignments = (
        StoredRoomAssignment(
            session_id=room.id,
            member_id=host.id,
            character_id="investigator",
            assigned_at=now,
        ),
        StoredRoomAssignment(
            session_id=room.id,
            member_id=guest.id,
            character_id="insider",
            assigned_at=now,
        ),
    )
    repository = _StartRepository((host, guest), assignments)

    revision = await service._start_room(  # noqa: SLF001
        repository,  # type: ignore[arg-type]
        RoomMutationContext(room=room, member=host),
    )

    assert revision == 12
    assert repository.required == (
        (host.id, "investigator"),
        (guest.id, "insider"),
    )
    assert repository.revision == 12
    assert repository.revoked is True
    assert repository.state is not None
    state = GameStateV2.model_validate_json(json.dumps(repository.state))
    required_ids = (str(host.id), str(guest.id))
    assert state.room.required_member_ids == required_ids
    assert tuple(state.players) == required_ids
    assert state.room_revision == 12
    assert state.private_by_member[str(host.id)].unlocked_chapter_ids == (
        "investigator-investigation",
    )
    assert state.private_by_member[str(guest.id)].unlocked_chapter_ids == ("insider-investigation",)
