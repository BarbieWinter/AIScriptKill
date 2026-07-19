from pathlib import Path
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import Checkpoint, empty_checkpoint
from sqlalchemy import CheckConstraint

from engine.core.checkpoint import (
    CheckpointAttemptFencedError,
    SupabaseSessionCheckpointSaver,
    checkpoint_config,
)
from engine.core.checkpoint_models import (
    CheckpointConfigError,
    CommandCheckpointContext,
    checkpoint_locator,
)
from engine.core.game_state import create_initial_state
from engine.core.script_engine import ScriptEngine
from engine.db.tables import session_checkpoints
from engine.tests.checkpoint_fakes import MemoryCheckpointSession
from engine.tests.stategraph_fixtures import state_graph_package

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260719000000_mp3_stale_recovery_fencing.sql"
)


def test_command_checkpoint_config_round_trips_attempt_lineage() -> None:
    thread_id = str(uuid4())
    command_id = str(uuid4())

    config = checkpoint_config(
        thread_id,
        "checkpoint-1",
        command_id=command_id,
        command_attempt=2,
    )

    assert checkpoint_locator(config) == checkpoint_locator(config)
    assert checkpoint_locator(config).thread_id == thread_id
    assert checkpoint_locator(config).checkpoint_id == "checkpoint-1"
    assert checkpoint_locator(config).command_id == command_id
    assert checkpoint_locator(config).command_attempt == 2


def test_command_checkpoint_context_validates_fence_and_lease() -> None:
    command_id = uuid4()

    assert CommandCheckpointContext(command_id, 2, 45) == CommandCheckpointContext(
        command_id=command_id,
        command_attempt=2,
        lease_seconds=45,
    )
    with pytest.raises(ValueError):
        CommandCheckpointContext(command_id, 0)
    with pytest.raises(ValueError):
        CommandCheckpointContext(command_id, 1, 0)


@pytest.mark.parametrize(
    ("command_id", "command_attempt", "field"),
    [
        (str(uuid4()), None, "command_attempt"),
        (None, 1, "command_id"),
        (str(uuid4()), 0, "command_attempt"),
        ("not-a-uuid", 1, "command_id"),
    ],
)
def test_command_checkpoint_config_rejects_incomplete_or_invalid_lineage(
    command_id: str | None,
    command_attempt: int | None,
    field: str,
) -> None:
    with pytest.raises(CheckpointConfigError) as exc_info:
        checkpoint_config(
            str(uuid4()),
            command_id=command_id,
            command_attempt=command_attempt,
        )

    assert exc_info.value.field == field


def test_checkpoint_attempt_fencing_migration_and_metadata_pair_command_tags() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "add column command_attempt integer" in sql
    assert "command_attempt > 0" in sql
    assert "command_id is null and command_attempt is null" in sql
    assert "command_id is not null and command_attempt is not null" in sql
    assert session_checkpoints.c.command_attempt.nullable is True

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in session_checkpoints.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "session_checkpoints_command_attempt_check" in checks
    assert "command_attempt > 0" in checks["session_checkpoints_command_attempt_check"]


def _checkpoint(checkpoint_id: str, stage: str) -> Checkpoint:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["channel_values"] = {"current_stage": stage}
    return checkpoint


async def test_tagged_checkpoint_write_renews_lease_and_preserves_lineage() -> None:
    db = MemoryCheckpointSession()
    session_id = uuid4()
    command_id = uuid4()
    db.activate_command_attempt(session_id, command_id, 2)
    saver = SupabaseSessionCheckpointSaver(db, lease_seconds=45)
    config = checkpoint_config(
        str(session_id),
        command_id=str(command_id),
        command_attempt=2,
    )

    stored = await saver.aput(config, _checkpoint("0001", "prologue"), {"source": "input"}, {})

    locator = checkpoint_locator(stored)
    assert locator.command_id == str(command_id)
    assert locator.command_attempt == 2
    assert db.rows[0].command_id == command_id
    assert db.rows[0].command_attempt == 2
    assert db.lease_renewals == [(session_id, command_id, 2, 45)]


async def test_stale_attempt_cannot_write_checkpoint_or_pending_writes() -> None:
    db = MemoryCheckpointSession()
    session_id = uuid4()
    command_id = uuid4()
    db.activate_command_attempt(session_id, command_id, 2)
    saver = SupabaseSessionCheckpointSaver(db)
    stale = checkpoint_config(
        str(session_id),
        "0001",
        command_id=str(command_id),
        command_attempt=1,
    )

    with pytest.raises(CheckpointAttemptFencedError):
        await saver.aput(stale, _checkpoint("0002", "act1"), {"source": "loop"}, {})
    with pytest.raises(CheckpointAttemptFencedError):
        await saver.aput_writes(stale, [("messages", ["stale"])], "task-1")

    assert db.rows == []
    assert db.writes == []
    assert db.commit_count == 0


async def test_latest_command_checkpoint_is_exact_to_attempt_lineage() -> None:
    db = MemoryCheckpointSession()
    session_id = uuid4()
    command_id = uuid4()
    saver = SupabaseSessionCheckpointSaver(db)

    db.activate_command_attempt(session_id, command_id, 1)
    attempt_one = checkpoint_config(
        str(session_id),
        command_id=str(command_id),
        command_attempt=1,
    )
    first = await saver.aput(
        attempt_one,
        _checkpoint("0001", "prologue"),
        {"source": "input"},
        {},
    )
    await saver.aput(first, _checkpoint("0003", "act1"), {"source": "loop"}, {})

    db.activate_command_attempt(session_id, command_id, 2)
    attempt_two = checkpoint_config(
        str(session_id),
        command_id=str(command_id),
        command_attempt=2,
    )
    await saver.aput(attempt_two, _checkpoint("0002", "review"), {"source": "input"}, {})

    latest_one = await saver.aget_latest_command_checkpoint(
        thread_id=str(session_id),
        command_id=str(command_id),
        command_attempt=1,
    )
    latest_two = await saver.aget_latest_command_checkpoint(
        thread_id=str(session_id),
        command_id=str(command_id),
        command_attempt=2,
    )
    latest_through_two = await saver.alatest_command_config_through_attempt(
        str(session_id),
        command_id,
        2,
    )
    latest_checkpoint_through_two = await saver.aget_latest_command_checkpoint(
        thread_id=str(session_id),
        command_id=command_id,
        max_attempt=2,
    )

    assert latest_one is not None
    assert latest_one.checkpoint["id"] == "0003"
    assert checkpoint_locator(latest_one.config).command_attempt == 1
    assert latest_two is not None
    assert latest_two.checkpoint["id"] == "0002"
    assert checkpoint_locator(latest_two.config).command_attempt == 2
    assert latest_through_two is not None
    assert checkpoint_locator(latest_through_two).checkpoint_id == "0003"
    assert checkpoint_locator(latest_through_two).command_attempt == 2
    assert latest_checkpoint_through_two is not None
    assert latest_checkpoint_through_two.checkpoint["id"] == "0003"
    assert checkpoint_locator(latest_checkpoint_through_two.config).command_attempt == 2

    wrong_command = await saver.aget_tuple(
        checkpoint_config(
            str(session_id),
            "0003",
            command_id=str(uuid4()),
            command_attempt=2,
        )
    )
    future_attempt = await saver.aget_tuple(
        checkpoint_config(
            str(session_id),
            "0002",
            command_id=str(command_id),
            command_attempt=1,
        )
    )
    assert wrong_command is None
    assert future_attempt is None


async def test_script_engine_runs_inspects_and_resumes_exact_command_checkpoint() -> None:
    package = state_graph_package()
    db = MemoryCheckpointSession()
    session_id = uuid4()
    command_id = uuid4()
    db.activate_command_attempt(session_id, command_id, 1)
    saver = SupabaseSessionCheckpointSaver(db)
    engine = ScriptEngine.from_package(package, checkpointer=saver)
    state = create_initial_state(
        session_id=str(session_id),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )
    command_config = checkpoint_config(
        str(session_id),
        command_id=str(command_id),
        command_attempt=1,
    )

    result, final_config = await engine.run_action_from(
        state,
        action_id="open_clue_board",
        config=command_config,
    )
    final_inspection = await engine.inspect_state(final_config)

    assert result["performed_actions"]
    assert final_inspection.state == result
    assert final_inspection.config == final_config
    assert final_inspection.quiescent is True
    assert checkpoint_locator(final_config).checkpoint_id is not None
    assert checkpoint_locator(final_config).command_id == str(command_id)

    history = [item async for item in saver.alist(command_config)]
    resumable = None
    for item in reversed(history):
        inspection = await engine.inspect_state(item.config)
        if not inspection.quiescent:
            resumable = item.config
            break
    assert resumable is not None

    resumed, resumed_config = await engine.resume_action(resumable)
    resumed_inspection = await engine.inspect_state(resumed_config)

    assert resumed["performed_actions"]
    assert resumed_inspection.state == resumed
    assert resumed_inspection.quiescent is True
    assert checkpoint_locator(resumed_config).command_attempt == 1

    db.activate_command_attempt(session_id, command_id, 2)
    predecessor_id = checkpoint_locator(resumable).checkpoint_id
    assert predecessor_id is not None
    reclaimed_config = checkpoint_config(
        str(session_id),
        predecessor_id,
        command_id=str(command_id),
        command_attempt=2,
    )

    recovered, recovered_config = await engine.resume_action(reclaimed_config)

    assert recovered["performed_actions"]
    assert checkpoint_locator(recovered_config).command_attempt == 2
    assert any(row.command_attempt == 2 for row in db.rows)
