"""Participant-safe cursor replay and bounded recovery coverage."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from engine.api.errors import ApiError
from engine.api.middleware.auth import VerifiedAnonymousPrincipal
from engine.api.schemas.multiplayer_rooms import ClosedRoomSnapshotV1, LobbyPackageSummary
from engine.repositories.multiplayer_room_models import StoredMultiplayerRoom, StoredRoomMember
from engine.services import room_event_replay


@dataclass
class _ReplayRepository:
    room: StoredMultiplayerRoom | None
    member: StoredRoomMember | None

    async def get_room(self, _session_id: UUID) -> StoredMultiplayerRoom | None:
        return self.room

    async def joined_member(
        self,
        _session_id: UUID,
        _principal_id: UUID,
    ) -> StoredRoomMember | None:
        return self.member


class _EventsRepository:
    def __init__(self, rows: Sequence[dict[str, object]], first_sequence: int | None) -> None:
        self.rows = tuple(rows)
        self.first_sequence = first_sequence
        self.calls: list[dict[str, object]] = []

    async def first_event_sequence(self, _session_id: UUID) -> int | None:
        return self.first_sequence

    async def list_participant_events(
        self,
        _session_id: UUID,
        after_sequence: int,
        limit: int,
        *,
        through_sequence: int,
        event_type: str | None = None,
    ) -> Sequence[dict[str, object]]:
        self.calls.append(
            {
                "after_sequence": after_sequence,
                "limit": limit,
                "through_sequence": through_sequence,
                "event_type": event_type,
            }
        )
        return tuple(
            row
            for row in self.rows
            if after_sequence < int(row["sequence"]) <= through_sequence
            and (event_type is None or row["event_type"] == event_type)
        )[:limit]

    async def has_event_after(
        self,
        _session_id: UUID,
        after_sequence: int,
        *,
        through_sequence: int,
        event_type: str | None = None,
    ) -> bool:
        return any(
            after_sequence < int(row["sequence"]) <= through_sequence
            and (event_type is None or row["event_type"] == event_type)
            for row in self.rows
        )


@pytest.fixture
def principal() -> VerifiedAnonymousPrincipal:
    return VerifiedAnonymousPrincipal(id=uuid4())


@pytest.fixture
def room(principal: VerifiedAnonymousPrincipal) -> StoredMultiplayerRoom:
    now = datetime.now(UTC)
    return StoredMultiplayerRoom(
        id=uuid4(),
        script_id="replay-test",
        status="closed",
        revision=4,
        event_head_sequence=4,
        state_schema_version=2,
        state={},
        runtime_package_version="1.0.0",
        runtime_package_snapshot={},
        runtime_package_sha256="0" * 64,
        created_at=now,
        started_at=None,
        closed_at=now,
    )


@pytest.fixture
def member(room: StoredMultiplayerRoom, principal: VerifiedAnonymousPrincipal) -> StoredRoomMember:
    return StoredRoomMember(
        id=uuid4(),
        session_id=room.id,
        principal_id=principal.id,
        room_role="host",
        ready_at=None,
        joined_at=room.created_at,
    )


@pytest.fixture
def snapshot(room: StoredMultiplayerRoom, member: StoredRoomMember) -> ClosedRoomSnapshotV1:
    assert room.closed_at is not None
    return ClosedRoomSnapshotV1(
        session_id=room.id,
        revision=room.revision,
        event_head_sequence=room.event_head_sequence,
        package=LobbyPackageSummary(script_id="replay-test", title="Replay Test", version="1.0.0"),
        self_member_id=str(member.id),
        closed_at=room.closed_at,
    )


def _row(sequence: int, *, event_type: str = "lobby.command_succeeded") -> dict[str, object]:
    payloads: dict[str, dict[str, object]] = {
        "lobby.command_succeeded": {"command_type": "room.ready"},
        "discussion.message": {
            "message_id": str(uuid4()),
            "stage_id": "investigation",
            "member_id": "member-a",
            "character_id": "investigator",
            "text": "公开讨论。",
        },
    }
    return {
        "id": uuid4(),
        "sequence": sequence,
        "revision": sequence,
        "event_type": event_type,
        "event_version": 1,
        "payload": payloads[event_type],
    }


@pytest.mark.asyncio
async def test_replay_returns_stable_ids_ascending_events_and_a_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    snapshot: ClosedRoomSnapshotV1,
) -> None:
    rows = (_row(1), _row(2), _row(3), _row(4))
    events = _EventsRepository(rows, first_sequence=1)
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay, "MultiplayerRoomRepository", lambda _db: _ReplayRepository(room, member)
    )
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: events)

    async def get_snapshot(*_args: object) -> ClosedRoomSnapshotV1:
        return snapshot

    monkeypatch.setattr(room_event_replay, "get_room_snapshot", get_snapshot)

    page = await room_event_replay.get_participant_room_events(
        str(room.id),
        after_sequence=1,
        limit=2,
        principal=principal,
        db=object(),  # type: ignore[arg-type]
    )

    assert [event.sequence for event in page.events] == [2, 3]
    assert [event.event_id for event in page.events] == [rows[1]["id"], rows[2]["id"]]
    assert page.snapshot == snapshot
    assert page.next_after_sequence == 3
    assert page.has_more is True
    assert page.reset_required is False
    assert events.calls == [
        {
            "after_sequence": 1,
            "limit": 2,
            "through_sequence": room.event_head_sequence,
            "event_type": None,
        }
    ]


@pytest.mark.asyncio
async def test_replay_old_retained_cursor_requires_snapshot_reset(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    snapshot: ClosedRoomSnapshotV1,
) -> None:
    events = _EventsRepository((_row(3), _row(4)), first_sequence=3)
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay, "MultiplayerRoomRepository", lambda _db: _ReplayRepository(room, member)
    )
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: events)

    async def get_snapshot(*_args: object) -> ClosedRoomSnapshotV1:
        return snapshot

    monkeypatch.setattr(room_event_replay, "get_room_snapshot", get_snapshot)

    page = await room_event_replay.get_participant_room_events(
        str(room.id),
        after_sequence=0,
        limit=100,
        principal=principal,
        db=object(),  # type: ignore[arg-type]
    )

    assert page.reset_required is True
    assert page.events == ()
    assert page.snapshot == snapshot
    assert page.available_from_sequence == 3
    assert events.calls == []


@pytest.mark.asyncio
async def test_replay_hides_missing_and_inaccessible_rooms_identically(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
) -> None:
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay,
        "MultiplayerRoomRepository",
        lambda _db: _ReplayRepository(None, None),
    )

    with pytest.raises(ApiError) as missing:
        await room_event_replay.get_participant_room_events(
            str(uuid4()),
            0,
            1,
            principal,
            object(),  # type: ignore[arg-type]
        )

    fake_room = SimpleNamespace(id=uuid4())
    monkeypatch.setattr(
        room_event_replay,
        "MultiplayerRoomRepository",
        lambda _db: _ReplayRepository(fake_room, None),
    )
    with pytest.raises(ApiError) as inaccessible:
        await room_event_replay.get_participant_room_events(
            str(fake_room.id),
            0,
            1,
            principal,
            object(),  # type: ignore[arg-type]
        )

    assert missing.value.status_code == inaccessible.value.status_code == 404
    assert missing.value.error.code == inaccessible.value.error.code == "ROOM_REPLAY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_replay_rejects_ahead_cursor(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    snapshot: ClosedRoomSnapshotV1,
) -> None:
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay, "MultiplayerRoomRepository", lambda _db: _ReplayRepository(room, member)
    )

    async def get_snapshot(*_args: object) -> ClosedRoomSnapshotV1:
        return snapshot

    monkeypatch.setattr(room_event_replay, "get_room_snapshot", get_snapshot)

    ahead_events = _EventsRepository((), first_sequence=None)
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: ahead_events)
    with pytest.raises(ApiError) as ahead:
        await room_event_replay.get_participant_room_events(
            str(room.id),
            room.event_head_sequence + 1,
            1,
            principal,
            object(),  # type: ignore[arg-type]
        )
    assert ahead.value.error.code == "INVALID_EVENT_CURSOR"


@pytest.mark.asyncio
async def test_replay_resets_for_a_purged_or_noncontiguous_retained_page(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    snapshot: ClosedRoomSnapshotV1,
) -> None:
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay, "MultiplayerRoomRepository", lambda _db: _ReplayRepository(room, member)
    )

    async def get_snapshot(*_args: object) -> ClosedRoomSnapshotV1:
        return snapshot

    monkeypatch.setattr(room_event_replay, "get_room_snapshot", get_snapshot)

    purged_events = _EventsRepository((), first_sequence=None)
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: purged_events)
    purged = await room_event_replay.get_participant_room_events(
        str(room.id),
        0,
        10,
        principal,
        object(),  # type: ignore[arg-type]
    )
    assert purged.reset_required is True
    assert purged.next_after_sequence == room.event_head_sequence
    assert purged.events == ()

    gapped_events = _EventsRepository((_row(3), _row(4)), first_sequence=1)
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: gapped_events)
    gapped = await room_event_replay.get_participant_room_events(
        str(room.id),
        0,
        10,
        principal,
        object(),  # type: ignore[arg-type]
    )
    assert gapped.reset_required is True
    assert gapped.next_after_sequence == room.event_head_sequence
    assert gapped.events == ()


@pytest.mark.asyncio
async def test_discussion_history_filters_non_discussion_events_and_pages(
    monkeypatch: pytest.MonkeyPatch,
    principal: VerifiedAnonymousPrincipal,
    room: StoredMultiplayerRoom,
    member: StoredRoomMember,
    snapshot: ClosedRoomSnapshotV1,
) -> None:
    rows = (
        _row(1),
        _row(2, event_type="discussion.message"),
        _row(3),
        _row(4, event_type="discussion.message"),
    )
    events = _EventsRepository(rows, first_sequence=1)
    monkeypatch.setattr(room_event_replay, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_event_replay, "MultiplayerRoomRepository", lambda _db: _ReplayRepository(room, member)
    )
    monkeypatch.setattr(room_event_replay, "SessionCommandRepository", lambda _db: events)

    async def get_snapshot(*_args: object) -> ClosedRoomSnapshotV1:
        return snapshot

    monkeypatch.setattr(room_event_replay, "get_room_snapshot", get_snapshot)
    page = await room_event_replay.get_participant_discussion_history(
        str(room.id),
        0,
        1,
        principal,
        object(),  # type: ignore[arg-type]
    )

    assert [event.sequence for event in page.events] == [2]
    assert page.next_after_sequence == 2
    assert page.has_more is True
    assert page.available_from_sequence == 0
    assert events.calls[0]["event_type"] == "discussion.message"


def test_event_projection_rejects_secret_or_unknown_payloads() -> None:
    with pytest.raises(ApiError) as exc_info:
        room_event_replay._participant_events(
            (
                {
                    "id": uuid4(),
                    "sequence": 1,
                    "revision": 1,
                    "event_type": "gameplay.command_succeeded",
                    "event_version": 1,
                    "payload": {"command_type": "settlement.submit", "option_id": "secret"},
                },
            )
        )

    assert exc_info.value.error.code == "ROOM_EVENT_INVALID"
