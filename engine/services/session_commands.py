"""MP-3 durable command coordination and HTTP replay projections."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import ApiError, bad_request, conflict, not_found
from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import (
    ActionRequest,
    CommandActionResponse,
    CommandReceiptResponse,
    SessionEvent,
    SessionEventPage,
)
from engine.db.tables import game_sessions
from engine.repositories.session_command_models import (
    CommandReceipt,
    canonical_command_payload,
    command_request_sha256,
)
from engine.repositories.session_command_repository import SessionCommandRepository
from engine.repositories.session_command_state import (
    canonical_game_state_payload,
    game_state_from_payload,
    game_state_sha256,
)
from engine.repositories.session_repository import SessionRepository
from engine.services.runtime_session import (
    LangGraphRuntimeActionExecutor,
    session_action_lock,
)
from engine.services.session_response_mappers import state_response


async def execute_command(
    session_id: str,
    payload: ActionRequest,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CommandActionResponse:
    """Claim, execute, and durably finalize one command under the session lock."""

    command_id = payload.command_id
    expected_revision = payload.expected_revision
    if command_id is None or expected_revision is None:
        raise bad_request("COMMAND_FIELDS_REQUIRED", "command_id 与 expected_revision 必须同时提供")

    session_uuid = _parse_session_id(session_id)
    commands = SessionCommandRepository(db)
    request_payload = canonical_command_payload(payload)
    request_hash = command_request_sha256(payload)

    async with session_action_lock(session_uuid):
        latest = await _authorized_session(session_uuid, current_user, db)

        existing = await commands.get_receipt(session_uuid, command_id)
        if existing is not None:
            if existing.request_sha256 != request_hash:
                raise conflict("COMMAND_ID_REUSE", "command_id 已绑定到不同的请求载荷")
            if existing.status == "processing":
                if _lease_is_active(existing.lease_expires_at):
                    raise conflict(
                        "COMMAND_IN_PROGRESS",
                        "该 command_id 仍在处理中，请查询 receipt 后重试",
                        {"command_id": str(command_id)},
                    )
                reclaimed = await commands.reclaim_expired_receipt(
                    session_uuid,
                    command_id,
                    existing.attempt_count,
                )
                if reclaimed is None:
                    raise conflict(
                        "COMMAND_IN_PROGRESS",
                        "该 command_id 已被另一个恢复进程领取",
                        {"command_id": str(command_id)},
                    )
                existing = reclaimed
                await db.commit()
            else:
                return _command_response(existing, latest.revision)

        claimed = existing
        if claimed is None:
            executor = LangGraphRuntimeActionExecutor()
            base_state, base_checkpoint_id = await executor.prepare_command_base_locked(latest, db)
            claimed = await commands.claim_receipt(
                session_id=session_uuid,
                command_id=command_id,
                request_payload=request_payload,
                request_sha256=request_hash,
                expected_revision=expected_revision,
                base_revision=latest.revision,
                base_state=canonical_game_state_payload(base_state),
                base_state_sha256=game_state_sha256(base_state),
                base_checkpoint_id=base_checkpoint_id,
            )
            if claimed is None:
                existing = await commands.get_receipt(session_uuid, command_id)
                if existing is not None and existing.request_sha256 != request_hash:
                    raise conflict("COMMAND_ID_REUSE", "command_id 已绑定到不同的请求载荷")
                raise conflict("COMMAND_IN_PROGRESS", "该 command_id 已被另一个请求领取")
            await db.commit()

        attempt_count = getattr(claimed, "attempt_count", 1)

        if expected_revision != latest.revision:
            await commands.reject_receipt(
                session_uuid,
                command_id,
                "SESSION_REVISION_CONFLICT",
                {
                    "expected_revision": expected_revision,
                    "current_revision": latest.revision,
                    "event_head_sequence": latest.event_head_sequence,
                },
                attempt_count=attempt_count,
            )
            await db.commit()
            raise conflict(
                "SESSION_REVISION_CONFLICT",
                "会话 revision 已变化，请先同步最新状态",
                {
                    "expected_revision": expected_revision,
                    "current_revision": latest.revision,
                    "event_head_sequence": latest.event_head_sequence,
                },
            )

        try:
            executor = LangGraphRuntimeActionExecutor()
            execution_kwargs: dict[str, object] = {}
            base_state = getattr(claimed, "base_state", None)
            base_state_sha256 = getattr(claimed, "base_state_sha256", None)
            if base_state is not None or base_state_sha256 is not None:
                if base_state is None or base_state_sha256 is None:
                    raise RuntimeError("durable command base state is incomplete")
                execution_kwargs = {
                    "command_id": command_id,
                    "command_attempt": attempt_count,
                    "base_checkpoint_id": getattr(claimed, "base_checkpoint_id", None),
                    "base_state": game_state_from_payload(base_state, base_state_sha256),
                }
            execution = await executor.execute_locked(
                latest,
                payload,
                db,
                **execution_kwargs,  # type: ignore[arg-type]
            )
        except ApiError as exc:
            await db.rollback()
            await commands.reject_receipt(
                session_uuid,
                command_id,
                exc.error.code,
                cast(dict[str, object], exc.error.details),
                attempt_count=attempt_count,
            )
            await db.commit()
            raise
        except Exception as exc:
            await db.rollback()
            has_checkpoint = getattr(commands, "has_command_checkpoint", None)
            checkpoint_exists = (
                await has_checkpoint(session_uuid, command_id)
                if has_checkpoint is not None
                else False
            )
            if checkpoint_exists:
                await commands.expire_lease(
                    session_uuid,
                    command_id,
                    attempt_count,
                )
            else:
                await commands.fail_receipt(
                    session_uuid,
                    command_id,
                    {"reason": exc.__class__.__name__},
                    attempt_count=attempt_count,
                )
            await db.commit()
            raise

        next_revision = latest.revision + 1
        next_sequence = latest.event_head_sequence + 1
        updated = cast(
            CursorResult[object],
            await db.execute(
                update(game_sessions)
                .where(
                    game_sessions.c.id == session_uuid,
                    game_sessions.c.revision == latest.revision,
                )
                .values(revision=next_revision, event_head_sequence=next_sequence)
            ),
        )
        if updated.rowcount != 1:
            await db.rollback()
            raise conflict("SESSION_REVISION_CONFLICT", "会话 revision 已变化，请先同步最新状态")

        result_payload = cast(dict[str, object], execution.response.model_dump(mode="json"))
        state_sha256 = game_state_sha256(execution.final_state)
        finalized = await commands.finalize_success(
            session_id=session_uuid,
            command_id=command_id,
            result=result_payload,
            revision=next_revision,
            event_sequence=next_sequence,
            event_payload={"result": result_payload},
            attempt_count=attempt_count,
            checkpoint_id=execution.checkpoint_id,
            state_sha256=state_sha256,
        )
        if not finalized:
            await db.rollback()
            raise conflict(
                "COMMAND_ATTEMPT_FENCED",
                "该 command attempt 已失去执行权，请查询 receipt",
                {"command_id": str(command_id), "attempt_count": attempt_count},
            )
        await db.commit()
        receipt = await commands.get_receipt(session_uuid, command_id)
        if receipt is None:
            raise RuntimeError("command receipt disappeared after finalize")
        return _command_response(receipt, next_revision)


async def get_command_receipt(
    session_id: str,
    command_id: UUID,
    current_user: CurrentUser,
    db: AsyncSession,
) -> CommandReceiptResponse:
    """Return a stored receipt after applying the normal session access check."""

    session_uuid = _parse_session_id(session_id)
    session = await _authorized_session(session_uuid, current_user, db)
    receipt = await SessionCommandRepository(db).get_receipt(session_uuid, command_id)
    if receipt is None:
        raise not_found("COMMAND_NOT_FOUND", "未找到指定 command receipt")
    return _receipt_response(receipt, session.revision)


async def get_session_events(
    session_id: str,
    after_sequence: int,
    limit: int,
    current_user: CurrentUser,
    db: AsyncSession,
) -> SessionEventPage:
    """Return ordered public events and a legacy-safe authoritative snapshot."""

    session_uuid = _parse_session_id(session_id)
    session = await _authorized_session(session_uuid, current_user, db)
    if after_sequence < 0:
        raise bad_request("INVALID_EVENT_CURSOR", "事件游标不能小于 0")
    if after_sequence > session.event_head_sequence:
        raise bad_request("INVALID_EVENT_CURSOR", "事件游标不能超过当前 event head")
    if limit < 1 or limit > 500:
        raise bad_request("INVALID_EVENT_LIMIT", "事件页大小必须在 1 到 500 之间")
    repository = SessionCommandRepository(db)
    rows = await repository.list_events(session_uuid, after_sequence, limit)
    events = [
        SessionEvent(
            sequence=cast(int, row["sequence"]),
            revision=cast(int, row["revision"]),
            command_id=cast(UUID, row["command_id"]),
            event_type=str(row["event_type"]),
            event_version=cast(int, row["event_version"]),
            payload=cast(dict[str, object], row["payload"]),
            state_sha256=cast(str | None, row["state_sha256"]),
        )
        for row in rows
    ]
    next_cursor = events[-1].sequence if events else after_sequence
    return SessionEventPage(
        revision=session.revision,
        event_head_sequence=session.event_head_sequence,
        snapshot=state_response(
            session,
            await SessionRepository(db).stage_name(session.script_id, session.state.current_stage),
        ).model_dump(mode="json"),
        events=events,
        next_after_sequence=next_cursor,
        has_more=next_cursor < session.event_head_sequence,
        reset_required=False,
    )


def _command_response(receipt: CommandReceipt, revision: int) -> CommandActionResponse:
    return CommandActionResponse(
        command_id=receipt.command_id,
        status=cast(Literal["succeeded", "rejected", "failed"], receipt.status),
        revision=receipt.result_revision if receipt.result_revision is not None else revision,
        event_sequence_from=receipt.event_sequence_from,
        event_sequence_to=receipt.event_sequence_to,
        result=receipt.result,
        error_code=receipt.error_code,
        error_details=receipt.error_details,
    )


def _receipt_response(receipt: CommandReceipt, revision: int) -> CommandReceiptResponse:
    return CommandReceiptResponse(
        command_id=receipt.command_id,
        status=receipt.status,
        revision=(
            receipt.result_revision
            if receipt.result_revision is not None
            else receipt.base_revision
            if receipt.base_revision is not None
            else revision
        ),
        event_sequence_from=receipt.event_sequence_from,
        event_sequence_to=receipt.event_sequence_to,
        result=receipt.result,
        error_code=receipt.error_code,
        error_details=receipt.error_details,
    )


def _lease_is_active(value: datetime | None) -> bool:
    if value is None:
        return False
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized > datetime.now(UTC)


async def _authorized_session(session_id: UUID, current_user: CurrentUser, db: AsyncSession):
    session = await SessionRepository(db).get_session(session_id)
    if session is None or session.mode != "legacy_single":
        raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
    if session.player_id is not None:
        actor = _actor_uuid(current_user)
        if actor != session.player_id:
            raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
    return session


def _parse_session_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise bad_request("INVALID_SESSION_ID", "session_id 必须是 UUID") from exc


def _actor_uuid(current_user: CurrentUser) -> UUID | None:
    if current_user.role == "anonymous":
        return None
    try:
        return UUID(current_user.subject)
    except ValueError:
        return None
