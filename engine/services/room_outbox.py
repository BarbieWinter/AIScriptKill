"""Relay transactional room events with committed leases and fenced acknowledgement."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from engine.db.tables import room_outbox, session_events

DEFAULT_OUTBOX_LEASE_SECONDS = 30
DEFAULT_OUTBOX_PUBLISH_TIMEOUT_SECONDS = 5.0
DEFAULT_OUTBOX_RETRY_BASE_SECONDS = 1
DEFAULT_OUTBOX_RETRY_MAX_SECONDS = 60
DEFAULT_OUTBOX_MAX_ATTEMPTS = 5
MAX_RELAY_WORKER_ID_LENGTH = 128
MAX_RELAY_ERROR_NAME_LENGTH = 128


@dataclass(frozen=True, slots=True)
class RoomOutboxMessage:
    """One immutable public event delivery; consumers deduplicate by event_id."""

    event_id: UUID
    session_id: UUID
    topic: str
    sequence: int
    revision: int
    event_type: str
    event_version: int
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class RoomOutboxLease:
    """A committed delivery claim fenced by one opaque token."""

    outbox_id: UUID
    lease_token: UUID
    worker_id: str
    attempts: int
    failure_attempts: int
    message: RoomOutboxMessage


@dataclass(frozen=True, slots=True)
class RoomOutboxBatchResult:
    """Aggregate result for one bounded relay cycle."""

    claimed: int
    published: int
    failed: int
    poisoned: int
    stale: int


@dataclass(frozen=True, slots=True)
class RoomOutboxHealth:
    """Aggregate operator health without room, member, event, or payload labels."""

    pending_count: int
    active_leases: int
    expired_leases: int
    poisoned_count: int
    retry_attempts: int
    oldest_pending_at: datetime | None
    last_published_at: datetime | None

    @property
    def oldest_pending_age_seconds(self) -> float | None:
        if self.oldest_pending_at is None:
            return None
        return max(0.0, (datetime.now(UTC) - self.oldest_pending_at).total_seconds())


class RoomOutboxPublisher(Protocol):
    async def publish(self, message: RoomOutboxMessage) -> None:
        """Publish one message or raise so the lease is retried or quarantined."""

        ...


FailureOutcome = Literal["retry", "poisoned", "stale"]
PublishOutcome = Literal["published", "failed", "poisoned", "stale"]


async def claim_room_outbox_batch(
    db: AsyncSession,
    *,
    worker_id: str,
    limit: int = 100,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
) -> tuple[RoomOutboxLease, ...]:
    """Claim eligible rows; the caller must commit before transport I/O."""

    normalized_worker_id = _validate_worker_id(worker_id)
    if limit < 1:
        raise ValueError("limit must be positive")
    if lease_seconds < 1:
        raise ValueError("lease_seconds must be positive")

    now = func.clock_timestamp()
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
                    room_outbox.c.poisoned_at.is_(None),
                    room_outbox.c.available_at <= now,
                    or_(
                        room_outbox.c.lease_token.is_(None),
                        room_outbox.c.lease_expires_at <= now,
                    ),
                )
                .order_by(room_outbox.c.available_at, room_outbox.c.id)
                .limit(limit)
                .with_for_update(of=room_outbox, skip_locked=True)
            )
        )
        .mappings()
        .all()
    )

    if len(rows) == 0:
        return ()

    outbox_ids = [cast(UUID, row["outbox_id"]) for row in rows]
    claimed_rows = (
        (
            await db.execute(
                update(room_outbox)
                .where(room_outbox.c.id.in_(outbox_ids))
                .values(
                    attempts=room_outbox.c.attempts + 1,
                    lease_token=func.gen_random_uuid(),
                    lease_owner=normalized_worker_id,
                    lease_expires_at=func.clock_timestamp() + timedelta(seconds=lease_seconds),
                    updated_at=func.now(),
                )
                .returning(
                    room_outbox.c.id.label("outbox_id"),
                    room_outbox.c.lease_token,
                    room_outbox.c.attempts,
                    room_outbox.c.failure_attempts,
                )
            )
        )
        .mappings()
        .all()
    )
    claimed_by_id = {cast(UUID, claimed["outbox_id"]): claimed for claimed in claimed_rows}
    return tuple(
        RoomOutboxLease(
            outbox_id=outbox_id,
            lease_token=cast(UUID, claimed_by_id[outbox_id]["lease_token"]),
            worker_id=normalized_worker_id,
            attempts=int(claimed_by_id[outbox_id]["attempts"]),
            failure_attempts=int(claimed_by_id[outbox_id]["failure_attempts"]),
            message=RoomOutboxMessage(
                event_id=cast(UUID, row["room_event_id"]),
                session_id=cast(UUID, row["session_id"]),
                topic=str(row["topic"]),
                sequence=int(row["sequence"]),
                revision=int(row["revision"]),
                event_type=str(row["event_type"]),
                event_version=int(row["event_version"]),
                payload=cast(dict[str, object], dict(row["payload"])),
            ),
        )
        for row, outbox_id in zip(rows, outbox_ids, strict=True)
    )


async def acknowledge_room_outbox_success(
    db: AsyncSession,
    lease: RoomOutboxLease,
) -> bool:
    """Mark one publication complete while this token remains the current lease."""

    result = cast(
        CursorResult[object],
        await db.execute(
            update(room_outbox)
            .where(
                room_outbox.c.id == lease.outbox_id,
                room_outbox.c.lease_token == lease.lease_token,
                room_outbox.c.lease_owner == lease.worker_id,
                room_outbox.c.published_at.is_(None),
                room_outbox.c.poisoned_at.is_(None),
            )
            .values(
                lease_token=None,
                lease_owner=None,
                lease_expires_at=None,
                published_at=func.now(),
                last_error=None,
                updated_at=func.now(),
            )
        ),
    )
    return result.rowcount == 1


async def acknowledge_room_outbox_failure(
    db: AsyncSession,
    lease: RoomOutboxLease,
    *,
    error_name: str,
    retry_base_seconds: int = DEFAULT_OUTBOX_RETRY_BASE_SECONDS,
    retry_max_seconds: int = DEFAULT_OUTBOX_RETRY_MAX_SECONDS,
    max_attempts: int = DEFAULT_OUTBOX_MAX_ATTEMPTS,
) -> FailureOutcome:
    """Record one transport failure while this token remains the current lease."""

    normalized_error = _bounded_error_name(error_name)
    _validate_retry_settings(
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
        max_attempts=max_attempts,
    )
    failure_attempts = lease.failure_attempts + 1
    poisoned = failure_attempts >= max_attempts
    values: dict[str, object] = {
        "failure_attempts": failure_attempts,
        "lease_token": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "last_error": normalized_error,
        "updated_at": func.now(),
    }
    if poisoned:
        values.update(
            poisoned_at=func.now(),
            poison_reason=normalized_error,
        )
    else:
        values["available_at"] = func.clock_timestamp() + timedelta(
            seconds=_retry_delay_seconds(
                attempts=failure_attempts,
                retry_base_seconds=retry_base_seconds,
                retry_max_seconds=retry_max_seconds,
            )
        )

    result = cast(
        CursorResult[object],
        await db.execute(
            update(room_outbox)
            .where(
                room_outbox.c.id == lease.outbox_id,
                room_outbox.c.lease_token == lease.lease_token,
                room_outbox.c.lease_owner == lease.worker_id,
                room_outbox.c.published_at.is_(None),
                room_outbox.c.poisoned_at.is_(None),
            )
            .values(**values)
        ),
    )
    if result.rowcount != 1:
        return "stale"
    return "poisoned" if poisoned else "retry"


async def publish_room_outbox_batch(
    factory: async_sessionmaker[AsyncSession],
    publisher: RoomOutboxPublisher,
    *,
    worker_id: str,
    limit: int = 100,
    lease_seconds: int = DEFAULT_OUTBOX_LEASE_SECONDS,
    publish_timeout_seconds: float = DEFAULT_OUTBOX_PUBLISH_TIMEOUT_SECONDS,
    retry_base_seconds: int = DEFAULT_OUTBOX_RETRY_BASE_SECONDS,
    retry_max_seconds: int = DEFAULT_OUTBOX_RETRY_MAX_SECONDS,
    max_attempts: int = DEFAULT_OUTBOX_MAX_ATTEMPTS,
) -> RoomOutboxBatchResult:
    """Commit claims, publish without row locks, then acknowledge in fresh transactions."""

    if publish_timeout_seconds <= 0:
        raise ValueError("publish_timeout_seconds must be positive")
    if lease_seconds <= publish_timeout_seconds:
        raise ValueError("lease_seconds must exceed publish_timeout_seconds")
    _validate_retry_settings(
        retry_base_seconds=retry_base_seconds,
        retry_max_seconds=retry_max_seconds,
        max_attempts=max_attempts,
    )

    async with factory() as claim_db:
        leases = await claim_room_outbox_batch(
            claim_db,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=lease_seconds,
        )
        await claim_db.commit()

    tasks: list[asyncio.Task[PublishOutcome]] = []
    async with asyncio.TaskGroup() as group:
        for lease in leases:
            tasks.append(
                group.create_task(
                    _publish_room_outbox_lease(
                        factory,
                        publisher,
                        lease,
                        publish_timeout_seconds=publish_timeout_seconds,
                        retry_base_seconds=retry_base_seconds,
                        retry_max_seconds=retry_max_seconds,
                        max_attempts=max_attempts,
                    )
                )
            )
    outcomes = [task.result() for task in tasks]
    return RoomOutboxBatchResult(
        claimed=len(leases),
        published=outcomes.count("published"),
        failed=outcomes.count("failed") + outcomes.count("poisoned"),
        poisoned=outcomes.count("poisoned"),
        stale=outcomes.count("stale"),
    )


async def _publish_room_outbox_lease(
    factory: async_sessionmaker[AsyncSession],
    publisher: RoomOutboxPublisher,
    lease: RoomOutboxLease,
    *,
    publish_timeout_seconds: float,
    retry_base_seconds: int,
    retry_max_seconds: int,
    max_attempts: int,
) -> PublishOutcome:
    try:
        await asyncio.wait_for(
            publisher.publish(lease.message),
            timeout=publish_timeout_seconds,
        )
    except Exception as exc:
        async with factory() as failure_db:
            outcome = await acknowledge_room_outbox_failure(
                failure_db,
                lease,
                error_name=exc.__class__.__name__,
                retry_base_seconds=retry_base_seconds,
                retry_max_seconds=retry_max_seconds,
                max_attempts=max_attempts,
            )
            await failure_db.commit()
        return "failed" if outcome == "retry" else outcome

    async with factory() as success_db:
        acknowledged = await acknowledge_room_outbox_success(success_db, lease)
        await success_db.commit()
    return "published" if acknowledged else "stale"


async def read_room_outbox_health(db: AsyncSession) -> RoomOutboxHealth:
    """Read aggregate queue health without exposing room-scoped identifiers."""

    now = func.clock_timestamp()
    pending = room_outbox.c.published_at.is_(None) & room_outbox.c.poisoned_at.is_(None)
    row = (
        await db.execute(
            select(
                func.count().filter(pending).label("pending_count"),
                func.count()
                .filter(
                    pending,
                    room_outbox.c.lease_token.is_not(None),
                    room_outbox.c.lease_expires_at > now,
                )
                .label("active_leases"),
                func.count()
                .filter(
                    pending,
                    room_outbox.c.lease_token.is_not(None),
                    room_outbox.c.lease_expires_at <= now,
                )
                .label("expired_leases"),
                func.count().filter(room_outbox.c.poisoned_at.is_not(None)).label("poisoned_count"),
                func.coalesce(func.sum(room_outbox.c.failure_attempts), 0).label(
                    "retry_attempts"
                ),
                func.min(room_outbox.c.created_at).filter(pending).label("oldest_pending_at"),
                func.max(room_outbox.c.published_at).label("last_published_at"),
            )
        )
    ).one()
    return RoomOutboxHealth(
        pending_count=int(row.pending_count),
        active_leases=int(row.active_leases),
        expired_leases=int(row.expired_leases),
        poisoned_count=int(row.poisoned_count),
        retry_attempts=int(row.retry_attempts),
        oldest_pending_at=cast(datetime | None, row.oldest_pending_at),
        last_published_at=cast(datetime | None, row.last_published_at),
    )


def _validate_worker_id(worker_id: str) -> str:
    normalized = worker_id.strip()
    if normalized == "":
        raise ValueError("worker_id must not be blank")
    if len(normalized) > MAX_RELAY_WORKER_ID_LENGTH:
        raise ValueError("worker_id is too long")
    return normalized


def _validate_retry_settings(
    *,
    retry_base_seconds: int,
    retry_max_seconds: int,
    max_attempts: int,
) -> None:
    if retry_base_seconds < 1:
        raise ValueError("retry_base_seconds must be positive")
    if retry_max_seconds < retry_base_seconds:
        raise ValueError("retry_max_seconds must be at least retry_base_seconds")
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")


def _retry_delay_seconds(
    *,
    attempts: int,
    retry_base_seconds: int,
    retry_max_seconds: int,
) -> int:
    exponent = min(max(attempts - 1, 0), 30)
    return min(retry_base_seconds * (2**exponent), retry_max_seconds)


def _bounded_error_name(error_name: str) -> str:
    normalized = error_name.strip() or "PublishError"
    return normalized[:MAX_RELAY_ERROR_NAME_LENGTH]
