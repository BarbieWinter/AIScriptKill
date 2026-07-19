from __future__ import annotations

import ast
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import get_type_hints
from uuid import uuid4

import pytest
from pydantic import TypeAdapter

from engine.api.errors import ApiError
from engine.api.middleware.auth import VerifiedAnonymousPrincipal
from engine.api.routes import sessions
from engine.contracts.multiplayer_v1.commands import (
    AssignCharacterCommand,
    AssignCharacterPayload,
    ConfirmReadCommand,
    MultiplayerCommand,
    StageCommandPayload,
)
from engine.contracts.multiplayer_v1.state import GameStateV2
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
        state_schema_version=2,
        runtime_package_version=package.package.version,
        runtime_package_snapshot=dict(snapshot.payload),
        runtime_package_sha256=snapshot.sha256,
        created_at=now,
        started_at=None,
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
            "command_id": uuid4(),
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
    assert db.commit_calls == 1


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
