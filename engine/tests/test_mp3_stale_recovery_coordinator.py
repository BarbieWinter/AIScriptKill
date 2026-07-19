from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from langgraph.checkpoint.base import Checkpoint, empty_checkpoint
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import ActionRequest, NpcResponse
from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.checkpoint_models import checkpoint_config, checkpoint_locator
from engine.core.game_state import GameState, create_initial_state
from engine.repositories.session_command_models import CommandReceipt, command_request_sha256
from engine.repositories.session_command_state import (
    canonical_game_state_payload,
    game_state_sha256,
)
from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.services import session_commands
from engine.services.runtime_session import RuntimeActionExecution
from engine.tests.checkpoint_fakes import MemoryCheckpointSession

SESSION_ID = UUID("00000000-0000-4000-8000-000000000201")
COMMAND_ID = UUID("00000000-0000-4000-8000-000000000202")
NOW = datetime(2026, 7, 19, 12, tzinfo=UTC)


async def test_command_checkpoint_recovery_searches_all_attempts_before_fresh_execution() -> None:
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)

    db.activate_command_attempt(SESSION_ID, COMMAND_ID, 1)
    attempt_one = checkpoint_config(
        str(SESSION_ID),
        command_id=str(COMMAND_ID),
        command_attempt=1,
    )
    first = await saver.aput(
        attempt_one,
        _checkpoint("0001", "prologue"),
        {"source": "input"},
        {},
    )
    await saver.aput(first, _checkpoint("0003", "act1"), {"source": "loop"}, {})

    db.activate_command_attempt(SESSION_ID, COMMAND_ID, 2)
    await saver.aput(
        checkpoint_config(
            str(SESSION_ID),
            command_id=str(COMMAND_ID),
            command_attempt=2,
        ),
        _checkpoint("0002", "review"),
        {"source": "input"},
        {},
    )

    recovery_config = await saver.alatest_command_config_through_attempt(
        str(SESSION_ID),
        COMMAND_ID,
        2,
    )
    assert recovery_config is not None

    latest = await saver.aget_tuple(recovery_config)

    assert latest is not None
    assert latest.checkpoint["id"] == "0003"
    assert checkpoint_locator(latest.config).command_attempt == 2


async def test_stale_command_without_any_command_checkpoint_uses_verified_stored_base_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    base_state = _base_state()
    stale = _receipt(
        request=request,
        attempt_count=1,
        lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC),
        base_state=base_state,
        base_state_sha256=game_state_sha256(base_state),
    )
    reclaimed = _receipt(
        request=request,
        attempt_count=2,
        lease_expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        base_state=base_state,
        base_state_sha256=game_state_sha256(base_state),
    )
    succeeded = _receipt(
        request=request,
        status="succeeded",
        attempt_count=2,
        lease_expires_at=None,
        base_state=base_state,
        base_state_sha256=game_state_sha256(base_state),
        result=_result(),
        result_revision=1,
        event_sequence_from=1,
        event_sequence_to=1,
    )
    repository = _repository(stale, reclaimed, succeeded)
    db = _db()
    execute_locked = AsyncMock(
        return_value=RuntimeActionExecution(
            response=_result(),
            final_state=base_state,
            checkpoint_id="final-checkpoint",
        )
    )
    _patch_coordinator(monkeypatch, repository, execute_locked)

    response = await session_commands.execute_command(
        str(SESSION_ID),
        request,
        CurrentUser(subject="anonymous", role="anonymous"),
        db,  # type: ignore[arg-type]
    )

    assert response.status == "succeeded"
    execute_locked.assert_awaited_once()
    execution = execute_locked.await_args
    assert execution is not None
    assert execution.kwargs["command_id"] == COMMAND_ID
    assert execution.kwargs["command_attempt"] == 2
    assert execution.kwargs["base_checkpoint_id"] == "base-checkpoint"
    assert execution.kwargs["base_state"] == base_state
    assert execution.kwargs["base_state"]["current_stage"] == "prologue"
    assert execution.kwargs["base_state"]["answer_key"] == {"culprit": "private"}


async def test_corrupt_stored_base_state_fails_closed_before_graph_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    base_state = _base_state()
    stale = _receipt(
        request=request,
        attempt_count=1,
        lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC),
        base_state=base_state,
        base_state_sha256="0" * 64,
    )
    reclaimed = _receipt(
        request=request,
        attempt_count=2,
        lease_expires_at=datetime(2100, 1, 1, tzinfo=UTC),
        base_state=base_state,
        base_state_sha256="0" * 64,
    )
    succeeded = _receipt(
        request=request,
        status="succeeded",
        attempt_count=2,
        lease_expires_at=None,
        base_state=base_state,
        base_state_sha256="0" * 64,
        result=_result(),
        result_revision=1,
        event_sequence_from=1,
        event_sequence_to=1,
    )
    repository = _repository(stale, reclaimed, succeeded)
    db = _db()
    execute_locked = AsyncMock(
        return_value=RuntimeActionExecution(
            response=_result(),
            final_state=base_state,
            checkpoint_id="final-checkpoint",
        )
    )
    _patch_coordinator(monkeypatch, repository, execute_locked)

    with pytest.raises(Exception, match="hash"):
        await session_commands.execute_command(
            str(SESSION_ID),
            request,
            CurrentUser(subject="anonymous", role="anonymous"),
            db,  # type: ignore[arg-type]
        )

    execute_locked.assert_not_awaited()


def _base_state() -> GameState:
    state = create_initial_state(
        session_id=str(SESSION_ID),
        script_id="minimal-case",
        player_id="anonymous",
        player_character_id="player",
        entry_stage="prologue",
    )
    state["answer_key"] = {"culprit": "private"}
    return state


def _request() -> ActionRequest:
    return ActionRequest(
        action="open_clue_board",
        command_id=COMMAND_ID,
        expected_revision=0,
    )


def _receipt(
    *,
    request: ActionRequest,
    attempt_count: int,
    lease_expires_at: datetime | None,
    base_state: GameState,
    base_state_sha256: str,
    status: str = "processing",
    result: NpcResponse | None = None,
    result_revision: int | None = None,
    event_sequence_from: int | None = None,
    event_sequence_to: int | None = None,
) -> CommandReceipt:
    return CommandReceipt(
        session_id=SESSION_ID,
        command_id=COMMAND_ID,
        request_payload={
            "action": "open_clue_board",
            "expected_revision": 0,
        },
        request_sha256=command_request_sha256(request),
        status=status,  # type: ignore[arg-type]
        expected_revision=0,
        base_revision=0,
        base_state=canonical_game_state_payload(base_state),
        base_state_sha256=base_state_sha256,
        result_revision=result_revision,
        result=result,
        error_code=None,
        error_details={},
        base_checkpoint_id="base-checkpoint",
        checkpoint_id=None,
        state_sha256=None,
        event_sequence_from=event_sequence_from,
        event_sequence_to=event_sequence_to,
        attempt_count=attempt_count,
        lease_expires_at=lease_expires_at,
        created_at=NOW - timedelta(minutes=1),
        updated_at=NOW,
    )


def _repository(
    existing: CommandReceipt,
    reclaimed: CommandReceipt,
    succeeded: CommandReceipt | None = None,
) -> SimpleNamespace:
    receipts = [existing]
    if succeeded is not None:
        receipts.append(succeeded)
    return SimpleNamespace(
        get_receipt=AsyncMock(side_effect=receipts),
        get_active_processing_receipt=AsyncMock(return_value=existing),
        reclaim_expired_receipt=AsyncMock(return_value=reclaimed),
        claim_receipt=AsyncMock(),
        has_command_checkpoint=AsyncMock(return_value=False),
        reject_receipt=AsyncMock(return_value=True),
        fail_receipt=AsyncMock(return_value=True),
        expire_lease=AsyncMock(return_value=True),
        finalize_success=AsyncMock(return_value=True),
    )


def _db() -> SimpleNamespace:
    return SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )


def _patch_coordinator(
    monkeypatch: pytest.MonkeyPatch,
    repository: SimpleNamespace,
    execute_locked: AsyncMock,
) -> None:
    class Lock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    def lock_factory(_session_id: UUID) -> Lock:
        return Lock()

    def repository_factory(_db: AsyncSession) -> SimpleNamespace:
        return repository

    monkeypatch.setattr(session_commands, "session_action_lock", lock_factory)
    monkeypatch.setattr(
        session_commands,
        "_authorized_session",
        AsyncMock(return_value=_stored_session()),
    )
    monkeypatch.setattr(session_commands, "SessionCommandRepository", repository_factory)
    monkeypatch.setattr(
        session_commands.LangGraphRuntimeActionExecutor,
        "execute_locked",
        execute_locked,
    )


def _stored_session() -> StoredSession:
    return StoredSession(
        id=SESSION_ID,
        script_id="minimal-case",
        player_id=None,
        player_character_id="player",
        state=SessionRuntimeState(current_stage="review"),
        status="in_progress",
        created_at=NOW,
        updated_at=NOW,
        revision=0,
        event_head_sequence=0,
    )


def _result() -> NpcResponse:
    return NpcResponse(
        type="npc_response",
        character_id="guide",
        text="继续调查。",
        emotion="calm",
        state_changes={},
        triggered_events=[],
        media_triggers=[],
    )


def _checkpoint(checkpoint_id: str, stage: str) -> Checkpoint:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["channel_values"] = {"current_stage": stage}
    return checkpoint
