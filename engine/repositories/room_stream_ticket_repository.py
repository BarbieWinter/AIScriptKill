"""Commit-free persistence for one-time authenticated room stream tickets."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from engine.db.tables import game_sessions, room_members, room_stream_tickets


@dataclass(frozen=True, slots=True)
class ConsumedRoomStreamTicket:
    """Identity and room cursor returned by one successful atomic consume."""

    session_id: UUID
    member_id: UUID
    principal_id: UUID
    protocol_version: int
    revision: int
    event_head_sequence: int


class RoomStreamTicketRepository:
    """Persist ticket digests without committing the injected transaction."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def database_wall_clock_now(self) -> datetime:
        """Return wall-clock database time after any room-lock wait."""

        return (await self.db.execute(select(func.clock_timestamp()))).scalar_one()

    async def revoke_active_for_member(
        self,
        *,
        session_id: UUID,
        member_id: UUID,
        now: datetime,
    ) -> None:
        await self.db.execute(
            update(room_stream_tickets)
            .where(
                room_stream_tickets.c.session_id == session_id,
                room_stream_tickets.c.member_id == member_id,
                room_stream_tickets.c.consumed_at.is_(None),
                room_stream_tickets.c.revoked_at.is_(None),
                room_stream_tickets.c.expires_at > now,
            )
            .values(revoked_at=now)
        )

    async def create_ticket(
        self,
        *,
        session_id: UUID,
        member_id: UUID,
        principal_id: UUID,
        ticket_hash: bytes,
        protocol_version: int,
        expires_at: datetime,
        created_at: datetime,
    ) -> bool:
        statement = (
            pg_insert(room_stream_tickets)
            .values(
                id=uuid4(),
                session_id=session_id,
                member_id=member_id,
                principal_id=principal_id,
                ticket_hash=ticket_hash,
                protocol_version=protocol_version,
                expires_at=expires_at,
                consumed_at=None,
                revoked_at=None,
                created_at=created_at,
            )
            .on_conflict_do_nothing(index_elements=[room_stream_tickets.c.ticket_hash])
            .returning(room_stream_tickets.c.id)
        )
        return (await self.db.execute(statement)).scalar_one_or_none() is not None

    async def consume_ticket(
        self,
        *,
        session_id: UUID,
        ticket_hash: bytes,
        protocol_version: int,
    ) -> ConsumedRoomStreamTicket | None:
        room = (
            (
                await self.db.execute(
                    select(
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                    )
                    .where(
                        game_sessions.c.id == session_id,
                        game_sessions.c.mode == "multiplayer_v1",
                    )
                    .with_for_update()
                )
            )
            .mappings()
            .one_or_none()
        )
        if room is None:
            return None

        statement = (
            update(room_stream_tickets)
            .where(
                room_stream_tickets.c.session_id == session_id,
                room_stream_tickets.c.ticket_hash == ticket_hash,
                room_stream_tickets.c.protocol_version == protocol_version,
                room_stream_tickets.c.consumed_at.is_(None),
                room_stream_tickets.c.revoked_at.is_(None),
                room_stream_tickets.c.expires_at > func.clock_timestamp(),
                room_members.c.id == room_stream_tickets.c.member_id,
                room_members.c.session_id == room_stream_tickets.c.session_id,
                room_members.c.principal_id == room_stream_tickets.c.principal_id,
                room_members.c.membership_status == "joined",
            )
            .values(consumed_at=func.clock_timestamp())
            .returning(
                room_stream_tickets.c.session_id,
                room_stream_tickets.c.member_id,
                room_stream_tickets.c.principal_id,
                room_stream_tickets.c.protocol_version,
            )
        )
        row = (await self.db.execute(statement)).mappings().one_or_none()
        if row is None:
            return None
        return ConsumedRoomStreamTicket(
            session_id=cast(UUID, row["session_id"]),
            member_id=cast(UUID, row["member_id"]),
            principal_id=cast(UUID, row["principal_id"]),
            protocol_version=int(row["protocol_version"]),
            revision=int(room["revision"]),
            event_head_sequence=int(room["event_head_sequence"]),
        )
