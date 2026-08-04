"""Authenticated participant-safe replay over immutable room events."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import bad_request, conflict, not_found
from engine.api.middleware.auth import VerifiedAnonymousPrincipal
from engine.api.schemas.multiplayer_rooms import RoomSnapshotV1
from engine.api.schemas.room_events import (
    DiscussionHistoryPage,
    ParticipantRoomEvent,
    ParticipantRoomEventPage,
)
from engine.repositories.multiplayer_room_models import StoredMultiplayerRoom
from engine.repositories.multiplayer_room_repository import MultiplayerRoomRepository
from engine.repositories.session_command_repository import SessionCommandRepository
from engine.services.multiplayer_feature import require_multiplayer_enabled
from engine.services.multiplayer_room_service import get_room_snapshot

MAX_ROOM_EVENT_PAGE_SIZE = 500
DEFAULT_ROOM_EVENT_PAGE_SIZE = 100
MAX_DISCUSSION_HISTORY_PAGE_SIZE = 200
DEFAULT_DISCUSSION_HISTORY_PAGE_SIZE = 100


@dataclass(frozen=True, slots=True)
class RoomReplayAuthorization:
    """A room and current joined member resolved only from the authenticated principal."""

    room: StoredMultiplayerRoom
    snapshot: RoomSnapshotV1


async def get_participant_room_events(
    session_id: str,
    after_sequence: int,
    limit: int,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> ParticipantRoomEventPage:
    """Return a bounded ascending event page and a current participant-safe snapshot."""

    authorization = await _authorize_replay(session_id, principal, db)
    _validate_cursor(after_sequence, authorization.snapshot.event_head_sequence)
    _validate_limit(limit, MAX_ROOM_EVENT_PAGE_SIZE)
    events = SessionCommandRepository(db)
    available_from = await events.first_event_sequence(authorization.room.id)
    available_from_sequence = available_from if available_from is not None else 0
    if _cursor_requires_reset(after_sequence, available_from_sequence):
        return ParticipantRoomEventPage(
            revision=authorization.snapshot.revision,
            event_head_sequence=authorization.snapshot.event_head_sequence,
            snapshot=authorization.snapshot,
            events=(),
            next_after_sequence=authorization.snapshot.event_head_sequence,
            has_more=False,
            reset_required=True,
            available_from_sequence=available_from_sequence,
        )
    rows = await events.list_participant_events(
        authorization.room.id,
        after_sequence,
        limit,
        through_sequence=authorization.snapshot.event_head_sequence,
    )
    page_events = _participant_events(rows)
    if _page_requires_reset(
        after_sequence,
        authorization.snapshot.event_head_sequence,
        page_events,
    ):
        return ParticipantRoomEventPage(
            revision=authorization.snapshot.revision,
            event_head_sequence=authorization.snapshot.event_head_sequence,
            snapshot=authorization.snapshot,
            events=(),
            next_after_sequence=authorization.snapshot.event_head_sequence,
            has_more=False,
            reset_required=True,
            available_from_sequence=available_from_sequence,
        )
    next_cursor = page_events[-1].sequence if page_events else after_sequence
    return ParticipantRoomEventPage(
        revision=authorization.snapshot.revision,
        event_head_sequence=authorization.snapshot.event_head_sequence,
        snapshot=authorization.snapshot,
        events=page_events,
        next_after_sequence=next_cursor,
        has_more=next_cursor < authorization.snapshot.event_head_sequence,
        available_from_sequence=available_from_sequence,
    )


async def get_participant_discussion_history(
    session_id: str,
    after_sequence: int,
    limit: int,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> DiscussionHistoryPage:
    """Page append-only public discussion events without exposing other event payloads."""

    authorization = await _authorize_replay(session_id, principal, db)
    _validate_cursor(after_sequence, authorization.snapshot.event_head_sequence)
    _validate_limit(limit, MAX_DISCUSSION_HISTORY_PAGE_SIZE)
    events = SessionCommandRepository(db)
    # A discussion may first occur after unrelated room events, so its first sequence
    # cannot identify retention loss. The full room-event replay endpoint owns reset
    # semantics; this filtered history endpoint remains an independently bounded view.
    available_from_sequence = 0
    rows = await events.list_participant_events(
        authorization.room.id,
        after_sequence,
        limit,
        through_sequence=authorization.snapshot.event_head_sequence,
        event_type="discussion.message",
    )
    page_events = _participant_events(rows)
    next_cursor = page_events[-1].sequence if page_events else after_sequence
    has_more = await events.has_event_after(
        authorization.room.id,
        next_cursor,
        through_sequence=authorization.snapshot.event_head_sequence,
        event_type="discussion.message",
    )
    return DiscussionHistoryPage(
        event_head_sequence=authorization.snapshot.event_head_sequence,
        events=page_events,
        next_after_sequence=next_cursor,
        has_more=has_more,
        available_from_sequence=available_from_sequence,
    )


async def _authorize_replay(
    session_id: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> RoomReplayAuthorization:
    require_multiplayer_enabled()
    room_id = _session_uuid(session_id)
    rooms = MultiplayerRoomRepository(db)
    room = await rooms.get_room(room_id)
    member = await rooms.joined_member(room_id, principal.id) if room is not None else None
    if room is None or member is None:
        raise not_found("ROOM_REPLAY_UNAVAILABLE", "房间事件回放不可用")
    snapshot = await get_room_snapshot(session_id, principal, db)
    return RoomReplayAuthorization(room=room, snapshot=snapshot)


def _session_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise bad_request("INVALID_SESSION_ID", "session_id 必须是 UUID") from exc


def _validate_cursor(after_sequence: int, event_head_sequence: int) -> None:
    if after_sequence < 0 or after_sequence > event_head_sequence:
        raise bad_request("INVALID_EVENT_CURSOR", "事件游标必须位于当前 event head 范围内")


def _validate_limit(limit: int, maximum: int) -> None:
    if limit < 1 or limit > maximum:
        raise bad_request("INVALID_EVENT_LIMIT", f"事件页大小必须在 1 到 {maximum} 之间")


def _cursor_requires_reset(after_sequence: int, available_from_sequence: int) -> bool:
    return available_from_sequence > 0 and after_sequence + 1 < available_from_sequence


def _participant_events(rows: Sequence[dict[str, object]]) -> tuple[ParticipantRoomEvent, ...]:
    try:
        return tuple(
            ParticipantRoomEvent(
                event_id=cast(UUID, row["id"]),
                sequence=cast(int, row["sequence"]),
                revision=cast(int, row["revision"]),
                event_type=str(row["event_type"]),
                event_version=cast(int, row["event_version"]),
                payload=_public_event_payload(str(row["event_type"]), row["payload"]),
            )
            for row in rows
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise conflict("ROOM_EVENT_INVALID", "房间事件格式无效") from exc


def _public_event_payload(event_type: str, value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("room event payload must be an object")
    payload = cast(Mapping[object, object], value)
    if any(not isinstance(key, str) for key in payload):
        raise ValueError("room event payload keys must be strings")
    allowed_keys: set[str] | None = {
        "lobby.command_succeeded": {"command_type"},
        "gameplay.command_succeeded": {"command_type", "stage_id", "actor_member_id"},
        "discussion.message": {"message_id", "stage_id", "member_id", "character_id", "text"},
        "room.incomplete_closed": {"command_type", "previous_status", "reason"},
    }.get(event_type)
    if allowed_keys is None or {str(key) for key in payload} != allowed_keys:
        raise ValueError("room event payload is not participant-safe")
    return cast(dict[str, object], dict(payload))


def _page_requires_reset(
    after_sequence: int,
    event_head_sequence: int,
    events: tuple[ParticipantRoomEvent, ...],
) -> bool:
    """Require snapshot recovery when retained rows cannot continue the exclusive cursor."""

    if after_sequence == event_head_sequence:
        return False
    expected = after_sequence + 1
    for event in events:
        if event.sequence != expected:
            return True
        expected += 1
    return not events
