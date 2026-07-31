"""Issue and consume one-time credentials for authenticated room streams."""

import secrets
from dataclasses import dataclass
from datetime import timedelta
from hashlib import sha256
from typing import Final
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.config import get_settings
from engine.api.errors import bad_request, conflict, not_found, service_unavailable
from engine.api.middleware.auth import VerifiedAnonymousPrincipal
from engine.api.schemas.multiplayer_rooms import CreateRoomStreamTicketResponse
from engine.contracts.multiplayer_v1.websocket import WS_PROTOCOL_VERSION
from engine.repositories.multiplayer_room_repository import MultiplayerRoomRepository
from engine.repositories.room_stream_ticket_repository import RoomStreamTicketRepository
from engine.services.multiplayer_feature import require_multiplayer_enabled

ROOM_STREAM_TICKET_TTL_SECONDS: Final = 30
ROOM_STREAM_TICKET_GENERATION_ATTEMPTS: Final = 3


@dataclass(frozen=True, slots=True)
class AuthenticatedRoomStream:
    """Server-derived identity and room cursor bound to one accepted stream."""

    session_id: UUID
    member_id: UUID
    principal_id: UUID
    protocol_version: int
    revision: int
    event_head_sequence: int


class RoomStreamAuthorizationError(ValueError):
    """Reject a stream credential without disclosing why authorization failed."""


async def issue_room_stream_ticket(
    session_id: str,
    principal: VerifiedAnonymousPrincipal,
    db: AsyncSession,
) -> CreateRoomStreamTicketResponse:
    """Issue one short-lived ticket for a currently joined room member."""

    require_multiplayer_enabled()
    if not get_settings().room_events_v1:
        raise service_unavailable(
            "ROOM_EVENTS_DISABLED",
            "房间事件流当前未启用",
        )

    room_id = _session_uuid(session_id)
    rooms = MultiplayerRoomRepository(db)
    tickets = RoomStreamTicketRepository(db)
    await rooms.advisory_lock(room_id)
    room = await rooms.lock_room(room_id)
    member = await rooms.joined_member(room_id, principal.id) if room is not None else None
    if room is None or member is None:
        raise not_found("ROOM_STREAM_UNAVAILABLE", "房间事件流不可用")

    now = await tickets.database_wall_clock_now()
    expires_at = now + timedelta(seconds=ROOM_STREAM_TICKET_TTL_SECONDS)
    await tickets.revoke_active_for_member(
        session_id=room.id,
        member_id=member.id,
        now=now,
    )
    plaintext = ""
    created = False
    for _ in range(ROOM_STREAM_TICKET_GENERATION_ATTEMPTS):
        plaintext = secrets.token_urlsafe(32)
        created = await tickets.create_ticket(
            session_id=room.id,
            member_id=member.id,
            principal_id=principal.id,
            ticket_hash=_ticket_digest(plaintext),
            protocol_version=WS_PROTOCOL_VERSION,
            expires_at=expires_at,
            created_at=now,
        )
        if created:
            break
    if not created:
        raise conflict("ROOM_STREAM_TICKET_COLLISION", "无法生成房间事件流凭证，请重试")

    await db.commit()
    return CreateRoomStreamTicketResponse(
        ticket=plaintext,
        protocol_version=WS_PROTOCOL_VERSION,
        expires_at=expires_at,
    )


async def consume_room_stream_ticket(
    session_id: UUID,
    ticket: str,
    protocol_version: int,
    db: AsyncSession,
) -> AuthenticatedRoomStream:
    """Atomically consume one ticket while revalidating its current membership."""

    settings = get_settings()
    if not settings.multiplayer_v1 or not settings.room_events_v1:
        raise RoomStreamAuthorizationError
    if protocol_version != WS_PROTOCOL_VERSION or not 32 <= len(ticket) <= 256:
        raise RoomStreamAuthorizationError

    rooms = MultiplayerRoomRepository(db)
    await rooms.advisory_lock(session_id)
    consumed = await RoomStreamTicketRepository(db).consume_ticket(
        session_id=session_id,
        ticket_hash=_ticket_digest(ticket),
        protocol_version=protocol_version,
    )
    if consumed is None:
        await db.rollback()
        raise RoomStreamAuthorizationError

    await db.commit()
    return AuthenticatedRoomStream(
        session_id=consumed.session_id,
        member_id=consumed.member_id,
        principal_id=consumed.principal_id,
        protocol_version=consumed.protocol_version,
        revision=consumed.revision,
        event_head_sequence=consumed.event_head_sequence,
    )


def _session_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise bad_request("INVALID_SESSION_ID", "session_id 必须是 UUID") from exc


def _ticket_digest(ticket: str) -> bytes:
    return sha256(ticket.encode("utf-8")).digest()
