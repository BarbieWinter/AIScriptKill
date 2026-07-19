"""SQLAlchemy Core persistence operations for MP-3 receipts and events."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from engine.db.tables import (
    session_checkpoints,
    session_command_receipts,
    session_events,
)
from engine.repositories.session_command_models import (
    CommandReceipt,
    ReceiptStatus,
    action_response_from_json,
)

DEFAULT_COMMAND_LEASE_SECONDS = 30


class SessionCommandRepository:
    """Own receipt/event SQL while leaving transaction ownership to services."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_receipt(self, session_id: UUID, command_id: UUID) -> CommandReceipt | None:
        row = (
            (
                await self.db.execute(
                    select(session_command_receipts).where(
                        session_command_receipts.c.session_id == session_id,
                        session_command_receipts.c.command_id == command_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _receipt_from_row(row) if row is not None else None

    async def get_active_processing_receipt(self, session_id: UUID) -> CommandReceipt | None:
        """Return the single processing receipt permitted for a session."""

        row = (
            (
                await self.db.execute(
                    select(session_command_receipts).where(
                        session_command_receipts.c.session_id == session_id,
                        session_command_receipts.c.status == "processing",
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        return _receipt_from_row(row) if row is not None else None

    async def claim_receipt(
        self,
        *,
        session_id: UUID,
        command_id: UUID,
        request_payload: dict[str, object],
        request_sha256: str,
        expected_revision: int,
        base_revision: int | None = None,
        base_state: dict[str, object] | None = None,
        base_state_sha256: str | None = None,
        base_checkpoint_id: str | None = None,
        lease_seconds: int = DEFAULT_COMMAND_LEASE_SECONDS,
        actor_principal_id: UUID | None = None,
        actor_member_id: UUID | None = None,
    ) -> CommandReceipt | None:
        row = (
            (
                await self.db.execute(
                    insert(session_command_receipts)
                    .values(
                        session_id=session_id,
                        command_id=command_id,
                        actor_principal_id=actor_principal_id,
                        actor_member_id=actor_member_id,
                        request_payload=request_payload,
                        request_sha256=request_sha256,
                        expected_revision=expected_revision,
                        base_revision=base_revision,
                        base_state=base_state,
                        base_state_sha256=base_state_sha256,
                        base_checkpoint_id=base_checkpoint_id,
                        status="processing",
                        attempt_count=1,
                        lease_expires_at=_lease_deadline(lease_seconds),
                        updated_at=func.now(),
                    )
                    .on_conflict_do_nothing()
                    .returning(session_command_receipts)
                )
            )
            .mappings()
            .one_or_none()
        )
        return _receipt_from_row(row) if row is not None else None

    async def reclaim_expired_receipt(
        self,
        session_id: UUID,
        command_id: UUID,
        expected_attempt: int,
        *,
        lease_seconds: int = DEFAULT_COMMAND_LEASE_SECONDS,
    ) -> CommandReceipt | None:
        """Atomically acquire a stale receipt and advance its fencing generation."""

        row = (
            (
                await self.db.execute(
                    update(session_command_receipts)
                    .where(
                        session_command_receipts.c.session_id == session_id,
                        session_command_receipts.c.command_id == command_id,
                        session_command_receipts.c.status == "processing",
                        session_command_receipts.c.attempt_count == expected_attempt,
                        session_command_receipts.c.lease_expires_at.is_not(None),
                        session_command_receipts.c.lease_expires_at <= func.now(),
                    )
                    .values(
                        attempt_count=session_command_receipts.c.attempt_count + 1,
                        lease_expires_at=_lease_deadline(lease_seconds),
                        updated_at=func.now(),
                    )
                    .returning(session_command_receipts)
                )
            )
            .mappings()
            .one_or_none()
        )
        return _receipt_from_row(row) if row is not None else None

    async def renew_lease(
        self,
        session_id: UUID,
        command_id: UUID,
        attempt_count: int,
        *,
        lease_seconds: int = DEFAULT_COMMAND_LEASE_SECONDS,
    ) -> bool:
        result = cast(
            CursorResult[object],
            await self.db.execute(
                _processing_update(session_id, command_id, attempt_count).values(
                    lease_expires_at=_lease_deadline(lease_seconds),
                    updated_at=func.now(),
                )
            ),
        )
        return result.rowcount == 1

    async def expire_lease(
        self,
        session_id: UUID,
        command_id: UUID,
        attempt_count: int,
    ) -> bool:
        """Make a recoverable attempt immediately reclaimable after request failure."""

        result = cast(
            CursorResult[object],
            await self.db.execute(
                _processing_update(session_id, command_id, attempt_count).values(
                    lease_expires_at=func.now(),
                    updated_at=func.now(),
                )
            ),
        )
        return result.rowcount == 1

    async def has_command_checkpoint(self, session_id: UUID, command_id: UUID) -> bool:
        return (
            await self.db.execute(
                select(session_checkpoints.c.thread_ts)
                .where(
                    session_checkpoints.c.session_id == session_id,
                    session_checkpoints.c.command_id == command_id,
                )
                .limit(1)
            )
        ).mappings().one_or_none() is not None

    async def reject_receipt(
        self,
        session_id: UUID,
        command_id: UUID,
        error_code: str,
        error_details: dict[str, object],
        *,
        attempt_count: int | None = None,
    ) -> bool:
        statement = _terminal_update(session_id, command_id, attempt_count).values(
            status="rejected",
            error_code=error_code,
            error_details=error_details,
            lease_expires_at=None,
            updated_at=func.now(),
            completed_at=func.now(),
        )
        result = cast(CursorResult[object], await self.db.execute(statement))
        return result.rowcount == 1

    async def fail_receipt(
        self,
        session_id: UUID,
        command_id: UUID,
        error_details: dict[str, object],
        *,
        attempt_count: int | None = None,
    ) -> bool:
        statement = _terminal_update(session_id, command_id, attempt_count).values(
            status="failed",
            error_code="COMMAND_FAILED",
            error_details=error_details,
            lease_expires_at=None,
            updated_at=func.now(),
            completed_at=func.now(),
        )
        result = cast(CursorResult[object], await self.db.execute(statement))
        return result.rowcount == 1

    async def finalize_success(
        self,
        *,
        session_id: UUID,
        command_id: UUID,
        result: dict[str, object],
        revision: int,
        event_sequence: int,
        event_payload: dict[str, object],
        attempt_count: int | None = None,
        checkpoint_id: str | None = None,
        state_sha256: str | None = None,
    ) -> bool:
        """Insert one public event and terminalize only the owning generation."""

        terminal = _terminal_update(session_id, command_id, attempt_count).values(
            status="succeeded",
            result=result,
            result_revision=revision,
            error_code=None,
            error_details={},
            checkpoint_id=checkpoint_id,
            state_sha256=state_sha256,
            event_sequence_from=event_sequence,
            event_sequence_to=event_sequence,
            lease_expires_at=None,
            updated_at=func.now(),
            completed_at=func.now(),
        )
        updated = cast(CursorResult[object], await self.db.execute(terminal))
        if updated.rowcount != 1:
            return False
        await self.db.execute(
            insert(session_events).values(
                session_id=session_id,
                sequence=event_sequence,
                revision=revision,
                command_id=command_id,
                event_type="command_succeeded",
                payload=event_payload,
                state_sha256=state_sha256,
            )
        )
        return True

    async def list_events(
        self,
        session_id: UUID,
        after_sequence: int,
        limit: int,
    ) -> Sequence[dict[str, object]]:
        rows = (
            (
                await self.db.execute(
                    select(session_events)
                    .where(
                        session_events.c.session_id == session_id,
                        session_events.c.sequence > after_sequence,
                    )
                    .order_by(session_events.c.sequence)
                    .limit(limit)
                )
            )
            .mappings()
            .all()
        )
        return cast(Sequence[dict[str, object]], rows)


def _lease_deadline(seconds: int):
    if seconds < 1:
        raise ValueError("lease_seconds must be positive")
    return func.now() + func.make_interval(0, 0, 0, 0, 0, 0, literal(seconds))


def _processing_update(session_id: UUID, command_id: UUID, attempt_count: int):
    return update(session_command_receipts).where(
        session_command_receipts.c.session_id == session_id,
        session_command_receipts.c.command_id == command_id,
        session_command_receipts.c.status == "processing",
        session_command_receipts.c.attempt_count == attempt_count,
    )


def _terminal_update(session_id: UUID, command_id: UUID, attempt_count: int | None):
    statement = update(session_command_receipts).where(
        session_command_receipts.c.session_id == session_id,
        session_command_receipts.c.command_id == command_id,
        session_command_receipts.c.status == "processing",
    )
    if attempt_count is not None:
        statement = statement.where(session_command_receipts.c.attempt_count == attempt_count)
    return statement


def _receipt_from_row(row: object) -> CommandReceipt:
    mapping = cast(dict[str, object], row)
    request_payload = cast(dict[str, object], mapping.get("request_payload") or {})
    return CommandReceipt(
        session_id=cast(UUID, mapping["session_id"]),
        command_id=cast(UUID, mapping["command_id"]),
        request_payload=request_payload,
        request_sha256=str(mapping["request_sha256"]),
        status=cast(ReceiptStatus, mapping["status"]),
        expected_revision=cast(int | None, mapping["expected_revision"]),
        base_revision=cast(int | None, mapping["base_revision"]),
        base_state=cast(dict[str, object] | None, mapping.get("base_state")),
        base_state_sha256=cast(str | None, mapping.get("base_state_sha256")),
        result_revision=cast(int | None, mapping["result_revision"]),
        result=action_response_from_json(mapping["result"]),
        error_code=cast(str | None, mapping["error_code"]),
        error_details=cast(dict[str, object], mapping["error_details"] or {}),
        base_checkpoint_id=cast(str | None, mapping.get("base_checkpoint_id")),
        checkpoint_id=cast(str | None, mapping.get("checkpoint_id")),
        state_sha256=cast(str | None, mapping.get("state_sha256")),
        event_sequence_from=cast(int | None, mapping["event_sequence_from"]),
        event_sequence_to=cast(int | None, mapping["event_sequence_to"]),
        attempt_count=cast(int, mapping.get("attempt_count", 1)),
        lease_expires_at=cast(datetime | None, mapping.get("lease_expires_at")),
        created_at=cast(datetime | None, mapping["created_at"]),
        updated_at=cast(datetime | None, mapping["updated_at"]),
        completed_at=cast(datetime | None, mapping.get("completed_at")),
    )
