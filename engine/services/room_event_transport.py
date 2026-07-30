"""Production transport adapters for public room-event references."""

from __future__ import annotations

import json
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from engine.services.room_outbox import RoomOutboxMessage

ROOM_EVENT_NOTIFICATION_PROTOCOL_VERSION = 1
ROOM_EVENT_TOPIC = "room.events.v1"
POSTGRES_NOTIFY_PAYLOAD_LIMIT_BYTES = 8000
_CHANNEL_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


class PostgresNotifyRoomOutboxPublisher:
    """Publish compact wake-up references through PostgreSQL LISTEN/NOTIFY."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        channel: str,
    ) -> None:
        if _CHANNEL_PATTERN.fullmatch(channel) is None:
            raise ValueError("invalid PostgreSQL notification channel")
        self._factory = factory
        self._channel = channel

    async def publish(self, message: RoomOutboxMessage) -> None:
        if message.topic != ROOM_EVENT_TOPIC:
            raise ValueError("unsupported room outbox topic")
        payload = room_event_notification_payload(message)
        async with self._factory() as db:
            await db.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": self._channel, "payload": payload},
            )
            await db.commit()


def room_event_notification_payload(message: RoomOutboxMessage) -> str:
    """Serialize only the identity needed to wake an authenticated replay reader."""

    payload = json.dumps(
        {
            "protocol_version": ROOM_EVENT_NOTIFICATION_PROTOCOL_VERSION,
            "topic": message.topic,
            "session_id": str(message.session_id),
            "event_id": str(message.event_id),
            "sequence": message.sequence,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    if len(payload.encode("utf-8")) >= POSTGRES_NOTIFY_PAYLOAD_LIMIT_BYTES:
        raise ValueError("room event notification payload exceeds PostgreSQL limit")
    return payload
