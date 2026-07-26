"""Publish transactional room events with at-least-once delivery semantics."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from engine.db.tables import room_outbox, session_events

DEFAULT_OUTBOX_RETRY_SECONDS = 5
DEFAULT_OUTBOX_PUBLISH_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class RoomOutboxMessage:
    """One immutable event delivery; consumers deduplicate by event_id."""

    event_id: UUID
    session_id: UUID
    topic: str
    sequence: int
    revision: int
    event_type: str
    event_version: int
    payload: dict[str, object]


class RoomOutboxPublisher(Protocol):
    async def publish(self, message: RoomOutboxMessage) -> None:
        """Publish one message or raise so the row remains retryable."""

        ...


async def publish_room_outbox_batch(
    db: AsyncSession,
    publisher: RoomOutboxPublisher,
    *,
    limit: int = 100,
    retry_seconds: int = DEFAULT_OUTBOX_RETRY_SECONDS,
    publish_timeout_seconds: float = DEFAULT_OUTBOX_PUBLISH_TIMEOUT_SECONDS,
) -> int:
    """Publish a locked pending batch and record each delivery attempt."""

    if limit < 1:
        raise ValueError("limit must be positive")
    if retry_seconds < 1:
        raise ValueError("retry_seconds must be positive")
    if publish_timeout_seconds <= 0:
        raise ValueError("publish_timeout_seconds must be positive")

    rows = (
        (
            await db.execute(
                select(
                    room_outbox.c.id.label("outbox_id"),
                    room_outbox.c.room_event_id,
                    room_outbox.c.session_id,
                    room_outbox.c.topic,
                    session_events.c.sequence,
                    session_events.c.revision,
                    session_events.c.event_type,
                    session_events.c.event_version,
                    session_events.c.payload,
                )
                .join(
                    session_events,
                    (session_events.c.session_id == room_outbox.c.session_id)
                    & (session_events.c.id == room_outbox.c.room_event_id),
                )
                .where(
                    room_outbox.c.published_at.is_(None),
                    room_outbox.c.available_at <= func.now(),
                )
                .order_by(room_outbox.c.available_at, room_outbox.c.id)
                .limit(limit)
                .with_for_update(of=room_outbox, skip_locked=True)
            )
        )
        .mappings()
        .all()
    )

    published = 0
    for row in rows:
        message = RoomOutboxMessage(
            event_id=cast(UUID, row["room_event_id"]),
            session_id=cast(UUID, row["session_id"]),
            topic=str(row["topic"]),
            sequence=int(row["sequence"]),
            revision=int(row["revision"]),
            event_type=str(row["event_type"]),
            event_version=int(row["event_version"]),
            payload=cast(dict[str, object], dict(row["payload"])),
        )
        try:
            await asyncio.wait_for(
                publisher.publish(message),
                timeout=publish_timeout_seconds,
            )
        except Exception as exc:
            await db.execute(
                update(room_outbox)
                .where(
                    room_outbox.c.id == row["outbox_id"],
                    room_outbox.c.published_at.is_(None),
                )
                .values(
                    attempts=room_outbox.c.attempts + 1,
                    available_at=func.clock_timestamp() + timedelta(seconds=retry_seconds),
                    last_error=exc.__class__.__name__,
                    updated_at=func.now(),
                )
            )
            continue
        await db.execute(
            update(room_outbox)
            .where(
                room_outbox.c.id == row["outbox_id"],
                room_outbox.c.published_at.is_(None),
            )
            .values(
                attempts=room_outbox.c.attempts + 1,
                published_at=func.now(),
                last_error=None,
                updated_at=func.now(),
            )
        )
        published += 1
    return published
