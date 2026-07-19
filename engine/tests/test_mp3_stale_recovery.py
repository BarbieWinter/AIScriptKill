from __future__ import annotations

import re
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import ClauseElement, Executable

from engine.api.middleware.auth import CurrentUser
from engine.api.schemas import ActionRequest, NpcResponse
from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.checkpoint_models import CheckpointAttemptFencedError
from engine.db.tables import session_checkpoints, session_command_receipts
from engine.repositories.session_command_models import CommandReceipt
from engine.repositories.session_command_repository import SessionCommandRepository
from engine.repositories.session_command_state import (
    canonical_game_state_payload,
    game_state_sha256,
)
from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.services import session_commands
from engine.services.runtime_session import RuntimeActionExecution
from engine.services.runtime_state_mappers import initial_game_state

SESSION_ID = UUID("00000000-0000-4000-8000-000000000101")
COMMAND_ID = UUID("00000000-0000-4000-8000-000000000102")
NOW = datetime(2026, 7, 19, 12, tzinfo=UTC)
RECOVERY_MIGRATION_PATTERN = "*_mp3_stale_recovery_fencing.sql"


def test_recovery_is_a_forward_migration_with_checkpoint_attempt_fencing() -> None:
    migration_root = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    base_migration = migration_root / "20260718010000_mp3_command_receipts_events.sql"
    recovery_migrations = sorted(migration_root.glob(RECOVERY_MIGRATION_PATTERN))

    assert len(recovery_migrations) == 1
    assert recovery_migrations[0].name > base_migration.name

    sql = _normalized_sql(recovery_migrations[0])
    assert "duplicate processing receipts require operator reconciliation" in sql
    assert "group by session_id having count(*) > 1" in sql
    assert "update public.session_command_receipts set lease_expires_at = now()" in sql
    assert "where status = 'processing' and lease_expires_at is null" in sql
    assert "session_command_receipts_processing_lease_check" in sql
    assert "status = 'processing' and lease_expires_at is not null" in sql
    assert "status <> 'processing' and lease_expires_at is null" in sql
    assert "drop index public.idx_session_command_receipts_processing" in sql
    assert "session_command_receipts(session_id, status, lease_expires_at)" in sql
    assert "alter table public.session_checkpoints add column command_attempt integer" in sql
    assert "update public.session_checkpoints set command_attempt = 1" in sql
    assert "where command_id is not null and command_attempt is null" in sql
    assert "session_checkpoints_command_attempt_check" in sql
    assert "command_id is null and command_attempt is null" in sql
    assert "command_id is not null and command_attempt is not null" in sql
    assert "command_attempt > 0" in sql
    assert "idx_session_checkpoints_session_command_attempt" in sql
    assert "add column base_state jsonb" in sql
    assert "add column base_state_sha256 text" in sql
    assert "session_command_receipts_base_state_check" in sql


def test_metadata_matches_checkpoint_attempt_and_base_state_fences() -> None:
    checkpoint_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in session_checkpoints.constraints
        if isinstance(constraint, CheckConstraint)
    }
    attempt_check = checkpoint_checks["session_checkpoints_command_attempt_check"]
    assert "command_id IS NULL AND command_attempt IS NULL" in attempt_check
    assert "command_attempt > 0" in attempt_check

    attempt_index = next(
        index
        for index in session_checkpoints.indexes
        if index.name == "idx_session_checkpoints_session_command_attempt"
    )
    assert tuple(column.name for column in attempt_index.columns) == (
        "session_id",
        "command_id",
        "command_attempt",
        "thread_ts",
    )

    receipt_checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in session_command_receipts.constraints
        if isinstance(constraint, CheckConstraint)
    }
    lease_check = receipt_checks["session_command_receipts_processing_lease_check"]
    assert "status = 'processing' AND lease_expires_at IS NOT NULL" in lease_check
    assert "status <> 'processing' AND lease_expires_at IS NULL" in lease_check
    processing_index = next(
        index
        for index in session_command_receipts.indexes
        if index.name == "idx_session_command_receipts_processing"
    )
    assert tuple(column.name for column in processing_index.columns) == (
        "session_id",
        "status",
        "lease_expires_at",
    )
    base_state_check = receipt_checks["session_command_receipts_base_state_check"]
    assert "base_state IS NULL AND base_state_sha256 IS NULL" in base_state_check
    assert "jsonb_typeof(base_state) = 'object'" in base_state_check


def test_command_receipt_exposes_recovery_fence_and_checkpoint_coordinates() -> None:
    names = {field.name for field in fields(CommandReceipt)}
    assert {
        "request_payload",
        "attempt_count",
        "lease_expires_at",
        "base_state",
        "base_state_sha256",
        "base_checkpoint_id",
        "checkpoint_id",
        "state_sha256",
    } <= names


async def test_reclaim_atomically_advances_only_the_expected_expired_attempt() -> None:
    row = _receipt_row(attempt_count=2, lease_expires_at=NOW + timedelta(seconds=30))
    db = RecordingCommandSession([RecordingResult([row])])
    repository = SessionCommandRepository(db)  # type: ignore[arg-type]

    reclaimed = await repository.reclaim_expired_receipt(
        SESSION_ID,
        COMMAND_ID,
        1,
    )

    assert reclaimed is not None
    assert reclaimed.attempt_count == 2
    assert reclaimed.lease_expires_at == NOW + timedelta(seconds=30)
    sql = _compiled_sql(db.statements[0])
    assert "UPDATE session_command_receipts" in sql
    assert "attempt_count=(session_command_receipts.attempt_count +" in sql
    assert "lease_expires_at <= now()" in sql
    assert "session_command_receipts.attempt_count =" in sql
    assert "'status_1': 'processing'" in sql
    assert " 1" in sql


@pytest.mark.parametrize(
    ("method_name", "args"),
    [
        (
            "reject_receipt",
            (SESSION_ID, COMMAND_ID, "ACTION_NOT_ALLOWED", {"reason": "blocked"}),
        ),
        ("fail_receipt", (SESSION_ID, COMMAND_ID, {"reason": "RuntimeError"})),
    ],
)
async def test_terminal_receipt_updates_reject_a_superseded_attempt(
    method_name: str,
    args: tuple[object, ...],
) -> None:
    db = RecordingCommandSession([RecordingResult([], rowcount=0)])
    repository = SessionCommandRepository(db)  # type: ignore[arg-type]
    method = getattr(repository, method_name)

    finalized = await method(*args, attempt_count=1)

    assert finalized is False
    assert len(db.statements) == 1
    sql = _compiled_sql(db.statements[0])
    assert "attempt_count" in sql
    assert "processing" in sql


async def test_stale_success_finalizer_cannot_publish_an_event() -> None:
    db = RecordingCommandSession([RecordingResult([], rowcount=0)])
    repository = SessionCommandRepository(db)  # type: ignore[arg-type]

    finalized = await repository.finalize_success(
        session_id=SESSION_ID,
        command_id=COMMAND_ID,
        attempt_count=1,
        result=_result().model_dump(mode="json"),
        revision=1,
        event_sequence=1,
        event_payload={"result": _result().model_dump(mode="json")},
    )

    assert finalized is False
    assert len(db.statements) == 1
    sql = _compiled_sql(db.statements[0])
    assert "UPDATE session_command_receipts" in sql
    assert "attempt_count" in sql
    assert "processing" in sql


async def test_checkpoint_config_tags_every_persisted_row_with_command_identity() -> None:
    db = RecordingCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)  # type: ignore[arg-type]
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "00000000-0000-6000-8000-000000000001"
    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(SESSION_ID),
            "command_id": str(COMMAND_ID),
            "command_attempt": 2,
        }
    }

    saved = await saver.aput(config, checkpoint, {"source": "loop"}, {})

    inserts = [statement for statement in db.statements if getattr(statement, "is_insert", False)]
    assert len(inserts) == 1
    params = inserts[0].compile(dialect=postgresql.dialect()).params
    assert params["command_id"] == COMMAND_ID
    assert params["command_attempt"] == 2
    assert saved.get("configurable", {}).get("command_id") == str(COMMAND_ID)
    assert saved.get("configurable", {}).get("command_attempt") == 2


async def test_checkpoint_write_is_rejected_after_its_command_attempt_is_superseded() -> None:
    db = RecordingCheckpointSession(command_attempt_owned=False)
    saver = SupabaseSessionCheckpointSaver(db)  # type: ignore[arg-type]
    checkpoint = empty_checkpoint()
    checkpoint["id"] = "00000000-0000-6000-8000-000000000002"
    config: RunnableConfig = {
        "configurable": {
            "thread_id": str(SESSION_ID),
            "command_id": str(COMMAND_ID),
            "command_attempt": 1,
        }
    }

    with pytest.raises(CheckpointAttemptFencedError):
        await saver.aput(config, checkpoint, {"source": "loop"}, {})

    assert not any(getattr(statement, "is_insert", False) for statement in db.statements)
    assert db.commit_count == 0
    assert db.rollback_count == 1


async def test_coordinator_reclaims_an_expired_attempt_and_fences_finalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)
    stale = _receipt(attempt_count=1, lease_expires_at=now - timedelta(seconds=1))
    reclaimed = _receipt(attempt_count=2, lease_expires_at=now + timedelta(seconds=30))
    succeeded = _receipt(
        status="succeeded",
        attempt_count=2,
        lease_expires_at=None,
        result=_result(),
        result_revision=1,
        event_sequence_from=1,
        event_sequence_to=1,
    )
    repository = SimpleNamespace(
        get_receipt=AsyncMock(side_effect=[stale, succeeded]),
        get_active_processing_receipt=AsyncMock(return_value=stale),
        claim_receipt=AsyncMock(),
        reclaim_expired_receipt=AsyncMock(return_value=reclaimed),
        has_command_checkpoint=AsyncMock(return_value=False),
        finalize_success=AsyncMock(return_value=True),
        reject_receipt=AsyncMock(return_value=True),
        fail_receipt=AsyncMock(return_value=True),
        expire_lease=AsyncMock(return_value=True),
    )
    db = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(rowcount=1)),
        commit=AsyncMock(),
        rollback=AsyncMock(),
    )

    class Lock:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, *_args: object) -> None:
            return None

    base_state = initial_game_state(_stored_session())
    execute_locked = AsyncMock(
        return_value=RuntimeActionExecution(
            response=_result(),
            final_state=base_state,
            checkpoint_id="final-checkpoint",
        )
    )
    monkeypatch.setattr(session_commands, "session_action_lock", lambda _id: Lock())
    monkeypatch.setattr(
        session_commands,
        "_authorized_session",
        AsyncMock(return_value=_stored_session()),
    )
    monkeypatch.setattr(session_commands, "SessionCommandRepository", lambda _db: repository)
    monkeypatch.setattr(
        session_commands.LangGraphRuntimeActionExecutor,
        "execute_locked",
        execute_locked,
    )

    response = await session_commands.execute_command(
        str(SESSION_ID),
        ActionRequest(
            action="open_clue_board",
            command_id=COMMAND_ID,
            expected_revision=0,
        ),
        CurrentUser(subject="anonymous", role="anonymous"),
        db,  # type: ignore[arg-type]
    )

    assert response.status == "succeeded"
    repository.reclaim_expired_receipt.assert_awaited_once_with(SESSION_ID, COMMAND_ID, 1)
    repository.claim_receipt.assert_not_awaited()
    execute_locked.assert_awaited_once()
    execution = execute_locked.await_args
    assert _attempt_argument(execution.args, execution.kwargs) == 2
    finalization = repository.finalize_success.await_args
    assert _attempt_argument(finalization.args, finalization.kwargs) == 2
    assert finalization.kwargs["checkpoint_id"] == "final-checkpoint"
    expected_state_hash = game_state_sha256(base_state)
    assert finalization.kwargs["state_sha256"] == expected_state_hash
    assert finalization.kwargs["event_payload"] == {"result": _result().model_dump(mode="json")}
    assert "final_state" not in finalization.kwargs["event_payload"]
    assert "answer_key" not in str(finalization.kwargs["event_payload"])


def _attempt_argument(args: tuple[object, ...], kwargs: dict[str, object]) -> int | None:
    for name in ("attempt_count", "command_attempt", "expected_attempt_count", "attempt"):
        value = kwargs.get(name)
        if type(value) is int:
            return value
    for value in args:
        if value == 2:
            return 2
    return None


def _receipt(
    *,
    status: str = "processing",
    attempt_count: int,
    lease_expires_at: datetime | None,
    result: NpcResponse | None = None,
    result_revision: int | None = None,
    event_sequence_from: int | None = None,
    event_sequence_to: int | None = None,
) -> CommandReceipt:
    base_state = initial_game_state(_stored_session())
    values: dict[str, object] = {
        "session_id": SESSION_ID,
        "command_id": COMMAND_ID,
        "request_payload": {
            "action": "open_clue_board",
            "expected_revision": 0,
        },
        "request_sha256": _request_hash(),
        "status": status,
        "expected_revision": 0,
        "base_revision": 0,
        "base_state": canonical_game_state_payload(base_state),
        "base_state_sha256": game_state_sha256(base_state),
        "result_revision": result_revision,
        "result": result,
        "error_code": None,
        "error_details": {},
        "event_sequence_from": event_sequence_from,
        "event_sequence_to": event_sequence_to,
        "attempt_count": attempt_count,
        "lease_expires_at": lease_expires_at,
        "base_checkpoint_id": None,
        "checkpoint_id": None,
        "state_sha256": None,
        "created_at": NOW - timedelta(minutes=1),
        "updated_at": NOW,
        "completed_at": NOW if status != "processing" else None,
    }
    return CommandReceipt(**values)  # type: ignore[arg-type]


def _receipt_row(*, attempt_count: int, lease_expires_at: datetime | None) -> dict[str, object]:
    return {
        "session_id": SESSION_ID,
        "command_id": COMMAND_ID,
        "request_payload": {
            "action": "open_clue_board",
            "expected_revision": 0,
        },
        "request_sha256": "a" * 64,
        "status": "processing",
        "expected_revision": 0,
        "base_revision": 0,
        "base_state": {"current_stage": "prologue"},
        "base_state_sha256": "b" * 64,
        "result_revision": None,
        "result": None,
        "error_code": None,
        "error_details": {},
        "event_sequence_from": None,
        "event_sequence_to": None,
        "attempt_count": attempt_count,
        "lease_expires_at": lease_expires_at,
        "base_checkpoint_id": None,
        "checkpoint_id": None,
        "state_sha256": None,
        "created_at": NOW - timedelta(minutes=1),
        "updated_at": NOW,
        "completed_at": None,
    }


def _stored_session() -> StoredSession:
    return StoredSession(
        id=SESSION_ID,
        script_id="minimal-case",
        player_id=None,
        player_character_id="player",
        state=SessionRuntimeState(current_stage="prologue"),
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


def _request_hash() -> str:
    payload = ActionRequest(
        action="open_clue_board",
        command_id=COMMAND_ID,
        expected_revision=0,
    )
    from engine.repositories.session_command_models import command_request_sha256

    return command_request_sha256(payload)


def _normalized_sql(path: Path) -> str:
    without_comments = re.sub(r"--[^\n]*", "", path.read_text(encoding="utf-8"))
    return " ".join(without_comments.lower().split())


def _compiled_sql(statement: Executable) -> str:
    assert isinstance(statement, ClauseElement)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = " ".join(compiled.string.split())
    return f"{sql} PARAMS {compiled.params!r}"


class RecordingCommandSession:
    def __init__(self, results: list["RecordingResult"]) -> None:
        self.results = results
        self.statements: list[Executable] = []

    async def execute(self, statement: Executable) -> "RecordingResult":
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("unexpected repository statement")
        return self.results.pop(0)


class RecordingCheckpointSession:
    def __init__(self, *, command_attempt_owned: bool = True) -> None:
        self.statements: list[Executable] = []
        self.command_attempt_owned = command_attempt_owned
        self.commit_count = 0
        self.rollback_count = 0

    async def execute(self, statement: Executable) -> "RecordingResult":
        self.statements.append(statement)
        compiled = statement.compile(dialect=postgresql.dialect())
        if (
            self.command_attempt_owned
            and getattr(statement, "is_update", False)
            and "session_command_receipts" in compiled.string
        ):
            return RecordingResult([{"command_id": COMMAND_ID}])
        return RecordingResult([])

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class RecordingResult:
    def __init__(self, rows: list[dict[str, object]], *, rowcount: int = 1) -> None:
        self.rows = rows
        self.rowcount = rowcount

    def mappings(self) -> "RecordingResult":
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, object]]:
        return self.rows
