from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from engine.api.errors import ApiError
from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import ActionRequest, NpcResponse
from engine.repositories.session_command_state import (
    canonical_game_state_payload,
    game_state_sha256,
)
from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.services import runtime_session, session_commands
from engine.services.runtime_session import RuntimeActionExecution
from engine.services.runtime_state_mappers import initial_game_state

SESSION_ID = UUID("00000000-0000-4000-8000-000000000001")
COMMAND_ID = UUID("00000000-0000-4000-8000-000000000002")


def stored_session(*, revision: int = 0, player_id: UUID | None = None) -> StoredSession:
    timestamp = datetime(2026, 7, 19, tzinfo=UTC)
    return StoredSession(
        id=SESSION_ID,
        script_id="minimal-case",
        player_id=player_id,
        player_character_id="player",
        state=SessionRuntimeState(current_stage="prologue"),
        status="in_progress",
        created_at=timestamp,
        updated_at=timestamp,
        revision=revision,
        event_head_sequence=revision,
    )


def _claimed_receipt() -> SimpleNamespace:
    base_state = initial_game_state(stored_session())
    return SimpleNamespace(
        status="processing",
        attempt_count=1,
        base_checkpoint_id=None,
        base_state=canonical_game_state_payload(base_state),
        base_state_sha256=game_state_sha256(base_state),
    )


@pytest.mark.asyncio
async def test_legacy_runtime_execute_commits_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = runtime_session.LangGraphRuntimeActionExecutor()
    result = NpcResponse(
        type="npc_response",
        character_id="guide",
        text="继续调查。",
        emotion="calm",
        state_changes={},
        triggered_events=[],
        media_triggers=[],
    )
    execute_locked = AsyncMock(
        return_value=RuntimeActionExecution(
            response=result,
            final_state=initial_game_state(stored_session()),
            checkpoint_id=None,
        )
    )
    commit = AsyncMock()
    monkeypatch.setattr(
        runtime_session.LangGraphRuntimeActionExecutor,
        "execute_locked",
        execute_locked,
    )

    class Lock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(runtime_session, "session_action_lock", lambda _id: Lock())

    returned = await executor.execute(
        stored_session(),
        ActionRequest(action="open_clue_board"),
        SimpleNamespace(commit=commit),  # type: ignore[arg-type]
    )

    assert returned == result
    commit.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_authenticated_legacy_claim_does_not_write_partial_member_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor_id = UUID("00000000-0000-4000-8000-000000000003")
    session = stored_session(player_id=actor_id)
    repository = SimpleNamespace(
        get_receipt=AsyncMock(return_value=None),
        claim_receipt=AsyncMock(return_value=SimpleNamespace(status="processing")),
        reject_receipt=AsyncMock(),
    )
    db = SimpleNamespace(commit=AsyncMock())

    class Lock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(session_commands, "session_action_lock", lambda _id: Lock())
    monkeypatch.setattr(session_commands, "_authorized_session", AsyncMock(return_value=session))
    monkeypatch.setattr(session_commands, "SessionCommandRepository", lambda _db: repository)
    base_state = initial_game_state(session)
    monkeypatch.setattr(
        session_commands.LangGraphRuntimeActionExecutor,
        "prepare_command_base_locked",
        AsyncMock(return_value=(base_state, None)),
    )

    with pytest.raises(ApiError) as raised:
        await session_commands.execute_command(
            str(SESSION_ID),
            ActionRequest(
                action="open_clue_board",
                command_id=COMMAND_ID,
                expected_revision=1,
            ),
            CurrentUser(subject=str(actor_id), role="authenticated"),
            db,  # type: ignore[arg-type]
        )

    assert raised.value.error.code == "SESSION_REVISION_CONFLICT"
    claim = repository.claim_receipt.await_args.kwargs
    assert "actor_principal_id" not in claim
    assert "actor_member_id" not in claim
    repository.reject_receipt.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "finalizer", "error_code"),
    [
        (ApiError(400, "ACTION_NOT_ALLOWED", "动作不可用"), "reject_receipt", "ACTION_NOT_ALLOWED"),
        (RuntimeError("boom"), "fail_receipt", "COMMAND_FAILED"),
    ],
)
async def test_command_failure_finalizes_terminal_receipt_without_advancing(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    finalizer: str,
    error_code: str,
) -> None:
    repository = SimpleNamespace(
        get_receipt=AsyncMock(return_value=None),
        claim_receipt=AsyncMock(return_value=_claimed_receipt()),
        reject_receipt=AsyncMock(),
        fail_receipt=AsyncMock(),
    )
    db = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    class Lock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    execute_locked = AsyncMock(side_effect=failure)
    monkeypatch.setattr(session_commands, "session_action_lock", lambda _id: Lock())
    monkeypatch.setattr(
        session_commands,
        "_authorized_session",
        AsyncMock(return_value=stored_session()),
    )
    monkeypatch.setattr(session_commands, "SessionCommandRepository", lambda _db: repository)
    base_state = initial_game_state(stored_session())
    monkeypatch.setattr(
        session_commands.LangGraphRuntimeActionExecutor,
        "prepare_command_base_locked",
        AsyncMock(return_value=(base_state, None)),
    )
    monkeypatch.setattr(
        session_commands.LangGraphRuntimeActionExecutor,
        "execute_locked",
        execute_locked,
    )

    with pytest.raises(type(failure)):
        await session_commands.execute_command(
            str(SESSION_ID),
            ActionRequest(
                action="open_clue_board",
                command_id=COMMAND_ID,
                expected_revision=0,
            ),
            CurrentUser(subject="anonymous", role="anonymous"),
            db,  # type: ignore[arg-type]
        )

    db.rollback.assert_awaited_once_with()
    terminal = getattr(repository, finalizer)
    terminal.assert_awaited_once()
    if finalizer == "reject_receipt":
        assert terminal.await_args.args[2] == error_code
        repository.fail_receipt.assert_not_awaited()
    else:
        assert terminal.await_args.args[2] == {"reason": "RuntimeError"}
        repository.reject_receipt.assert_not_awaited()
    assert db.commit.await_count == 2
