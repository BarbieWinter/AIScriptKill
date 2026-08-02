"""Supervise bounded room-event outbox relay cycles outside request workers."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from engine.services.room_outbox import (
    RoomOutboxBatchResult,
    RoomOutboxHealth,
    RoomOutboxPublisher,
    publish_room_outbox_batch,
    read_room_outbox_health,
)


@dataclass(frozen=True, slots=True)
class RoomEventRelayConfig:
    batch_size: int
    poll_seconds: float
    lease_seconds: int
    publish_timeout_seconds: float
    retry_base_seconds: int
    retry_max_seconds: int
    max_attempts: int

    def __post_init__(self) -> None:
        if self.batch_size < 1:
            raise ValueError("batch_size must be positive")
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be positive")
        if self.lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        if self.publish_timeout_seconds <= 0:
            raise ValueError("publish_timeout_seconds must be positive")
        if self.lease_seconds <= self.publish_timeout_seconds:
            raise ValueError("lease_seconds must exceed publish_timeout_seconds")
        if self.retry_base_seconds < 1:
            raise ValueError("retry_base_seconds must be positive")
        if self.retry_max_seconds < self.retry_base_seconds:
            raise ValueError("retry_max_seconds must be at least retry_base_seconds")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")


@dataclass(slots=True)
class RoomEventRelayStatus:
    running: bool = False
    ready: bool = False
    last_cycle_at: datetime | None = None
    last_cycle_error: str | None = None
    last_batch: RoomOutboxBatchResult | None = None


@dataclass(frozen=True, slots=True)
class RoomEventRelayHealth:
    running: bool
    ready: bool
    last_cycle_at: datetime | None
    last_cycle_error: str | None
    last_batch: RoomOutboxBatchResult | None
    queue: RoomOutboxHealth

    def payload(self) -> dict[str, object]:
        result: dict[str, object] = {
            "running": self.running,
            "pending_count": self.queue.pending_count,
            "active_leases": self.queue.active_leases,
            "expired_leases": self.queue.expired_leases,
            "poisoned_count": self.queue.poisoned_count,
            "retry_attempts": self.queue.retry_attempts,
            "oldest_pending_age_seconds": self.queue.oldest_pending_age_seconds,
            "last_cycle_at": _datetime_value(self.last_cycle_at),
            "last_published_at": _datetime_value(self.queue.last_published_at),
        }
        if self.last_cycle_error is not None:
            result["last_error"] = self.last_cycle_error
        if self.last_batch is not None:
            result["last_batch"] = {
                "claimed": self.last_batch.claimed,
                "published": self.last_batch.published,
                "failed": self.last_batch.failed,
                "poisoned": self.last_batch.poisoned,
                "stale": self.last_batch.stale,
            }
        return result


class RoomEventRelay:
    """Continuously relay outbox rows with bounded idle and publication waits."""

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        publisher: RoomOutboxPublisher,
        *,
        worker_id: str,
        config: RoomEventRelayConfig,
    ) -> None:
        self._factory = factory
        self._publisher = publisher
        self._worker_id = worker_id
        self._config = config
        self.status = RoomEventRelayStatus()

    async def run_once(self) -> RoomOutboxBatchResult:
        return await publish_room_outbox_batch(
            self._factory,
            self._publisher,
            worker_id=self._worker_id,
            limit=self._config.batch_size,
            lease_seconds=self._config.lease_seconds,
            publish_timeout_seconds=self._config.publish_timeout_seconds,
            retry_base_seconds=self._config.retry_base_seconds,
            retry_max_seconds=self._config.retry_max_seconds,
            max_attempts=self._config.max_attempts,
        )

    def record_cycle(self, result: RoomOutboxBatchResult) -> None:
        """Update readiness without letting idle cycles hide publication failures."""

        first_cycle = self.status.last_cycle_at is None
        self.status.last_batch = result
        if result.failed > 0:
            self.status.last_cycle_error = "PublicationFailed"
            self.status.ready = False
        elif result.published > 0 or first_cycle:
            self.status.last_cycle_error = None
            self.status.ready = True
        self.status.last_cycle_at = datetime.now(UTC)

    async def run(self, stop: asyncio.Event) -> None:
        if self.status.running:
            raise RuntimeError("room event relay is already running")
        self.status.running = True
        self.status.ready = False
        try:
            while not stop.is_set():
                try:
                    result = await self.run_once()
                except Exception as exc:
                    self.status.last_batch = None
                    self.status.last_cycle_error = exc.__class__.__name__
                    self.status.ready = False
                    self.status.last_cycle_at = datetime.now(UTC)
                    raise
                else:
                    self.record_cycle(result)
                if stop.is_set():
                    break
                try:
                    await asyncio.wait_for(stop.wait(), timeout=self._config.poll_seconds)
                except TimeoutError:
                    pass
        finally:
            self.status.running = False
            self.status.ready = False

    async def health(self) -> RoomEventRelayHealth:
        async with self._factory() as db:
            queue = await read_room_outbox_health(db)
        return RoomEventRelayHealth(
            running=self.status.running,
            ready=self.status.ready,
            last_cycle_at=self.status.last_cycle_at,
            last_cycle_error=self.status.last_cycle_error,
            last_batch=self.status.last_batch,
            queue=queue,
        )


def _datetime_value(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
