import asyncio
import json
import os
import signal
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table, delete, func, insert, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.event_bus import EventActionSink
from engine.core.game_state import create_initial_state
from engine.core.package_schema import JsonMapping
from engine.core.script_engine import ScriptEngine
from engine.db.session import build_async_database_url, build_connect_args
from engine.db.tables import (
    game_sessions,
    script_packages,
    session_checkpoint_writes,
    session_checkpoints,
)
from engine.tests.stategraph_fixtures import state_graph_package

DATABASE_URL_ENV = "AISCRIPTKILL_PROCESS_RECOVERY_DB_URL"


@pytest.mark.skipif(os.getenv(DATABASE_URL_ENV) is None, reason="requires a disposable Postgres")
async def test_stategraph_recovers_after_worker_is_killed() -> None:
    # 给定：真实游戏会话，以及拥有独立数据库连接的工作进程。
    database_url = _required_environment(DATABASE_URL_ENV)
    db_engine = _database_engine(database_url)
    script_id = f"checkpoint-process-{uuid4().hex}"
    session_id = uuid4()
    await _seed_session(db_engine, script_id, session_id)
    writer: asyncio.subprocess.Process | None = None
    try:
        writer = await _start_worker("write", database_url, script_id, session_id)
        written = await _read_worker_result(writer)
        assert written["status"] == "in_graph"
        assert written["action"] == "save_checkpoint"
        assert written["idempotency_key"] == (f"{session_id}:stage:prologue:exit:0")

        # 当：接收器仍阻塞在阶段退出节点时，不运行关闭钩子并直接终止进程。
        writer.kill()
        return_code = await writer.wait()
        if os.name == "nt":
            assert return_code != 0
        else:
            assert return_code == -signal.SIGKILL
        writer = None
        restored = await _run_worker("restore", database_url, script_id, session_id)

        # 则：另一个进程恢复最新图状态，并能提交下一回合。
        assert restored == {
            "status": "continued",
            "restored_stage": "prologue",
            "restored_next_stage": None,
            "continued_stage": "act1",
            "restored_performed_actions": 1,
            "continued_performed_actions": 2,
        }
        checkpoint_count, write_count = await _checkpoint_counts(db_engine, session_id)
        assert checkpoint_count > 0
        assert write_count > 0
    finally:
        if writer is not None and writer.returncode is None:
            writer.kill()
            await writer.wait()
        await _remove_script(db_engine, script_id)
        await db_engine.dispose()


async def _worker(phase: str) -> None:
    database_url = _required_environment(DATABASE_URL_ENV)
    script_id = _required_environment("AISCRIPTKILL_PROCESS_RECOVERY_SCRIPT_ID")
    session_id = UUID(_required_environment("AISCRIPTKILL_PROCESS_RECOVERY_SESSION_ID"))
    db_engine = _database_engine(database_url)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    package = state_graph_package()
    package = replace(package, package=replace(package.package, id=script_id))
    try:
        async with session_factory() as db:
            graph = ScriptEngine.from_package(
                package,
                checkpointer=SupabaseSessionCheckpointSaver(db),
            )
            if phase == "write":
                state = create_initial_state(
                    session_id=str(session_id),
                    script_id=script_id,
                    player_id=str(uuid4()),
                    player_character_id="player",
                    entry_stage="prologue",
                )
                # 先提交一个完整回合，确保强杀后存在可恢复的稳定基线。
                state = await graph.run_action(
                    state,
                    action_id="open_clue_board",
                    thread_id=str(session_id),
                )
                blocking_graph = ScriptEngine.from_package(
                    package,
                    event_sink=BlockingEventSink(),
                    checkpointer=SupabaseSessionCheckpointSaver(db),
                )
                await blocking_graph.run_action(
                    state,
                    action_id="request_advance",
                    thread_id=str(session_id),
                )
                return
            if phase == "restore":
                restored = await graph.restore_state(thread_id=str(session_id))
                if restored is None:
                    raise RuntimeError("worker could not restore the persisted checkpoint")
                continued = await graph.run_action(
                    restored,
                    action_id="request_advance",
                    thread_id=str(session_id),
                )
                _print_result(
                    {
                        "status": "continued",
                        "restored_stage": restored["current_stage"],
                        "restored_next_stage": restored["next_stage"],
                        "continued_stage": continued["current_stage"],
                        "restored_performed_actions": len(restored["performed_actions"]),
                        "continued_performed_actions": len(continued["performed_actions"]),
                    }
                )
                return
            raise ValueError(f"unsupported worker phase: {phase}")
    finally:
        await db_engine.dispose()


class BlockingEventSink(EventActionSink):
    """在阶段退出副作用内建立父进程可观察的确定性强杀点。"""

    async def execute(
        self,
        action: str,
        payload: JsonMapping,
        *,
        idempotency_key: str,
    ) -> None:
        _ = payload
        if action != "save_checkpoint":
            return
        _print_result(
            {
                "status": "in_graph",
                "action": action,
                "idempotency_key": idempotency_key,
            }
        )
        await asyncio.Event().wait()


async def _start_worker(
    phase: str,
    database_url: str,
    script_id: str,
    session_id: UUID,
) -> asyncio.subprocess.Process:
    environment = os.environ.copy()
    environment[DATABASE_URL_ENV] = database_url
    environment["AISCRIPTKILL_PROCESS_RECOVERY_SCRIPT_ID"] = script_id
    environment["AISCRIPTKILL_PROCESS_RECOVERY_SESSION_ID"] = str(session_id)
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "engine.tests.test_checkpoint_process_recovery",
        "--worker",
        phase,
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def _run_worker(
    phase: str,
    database_url: str,
    script_id: str,
    session_id: UUID,
) -> dict[str, Any]:
    worker = await _start_worker(phase, database_url, script_id, session_id)
    stdout, stderr = await asyncio.wait_for(worker.communicate(), timeout=30)
    if worker.returncode != 0:
        raise AssertionError(stderr.decode("utf-8", errors="replace"))
    return _decode_worker_result(stdout)


async def _read_worker_result(worker: asyncio.subprocess.Process) -> dict[str, Any]:
    if worker.stdout is None:
        raise AssertionError("worker stdout pipe is unavailable")
    line = await asyncio.wait_for(worker.stdout.readline(), timeout=30)
    if line == b"":
        await worker.wait()
        if worker.stderr is None:
            raise AssertionError("worker exited before reporting a result")
        stderr = await worker.stderr.read()
        raise AssertionError(stderr.decode("utf-8", errors="replace"))
    return _decode_worker_result(line)


def _decode_worker_result(raw: bytes) -> dict[str, Any]:
    decoded: object = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise AssertionError("worker returned an invalid JSON object")
    decoded_mapping = cast(dict[object, object], decoded)
    if not all(isinstance(key, str) for key in decoded_mapping):
        raise AssertionError("worker returned an invalid JSON object")
    return cast(dict[str, Any], decoded_mapping)


def _print_result(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=True), flush=True)


def _database_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        build_async_database_url(database_url),
        connect_args=build_connect_args(database_url),
    )


async def _seed_session(db_engine: AsyncEngine, script_id: str, session_id: UUID) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            insert(script_packages).values(
                id=script_id,
                name="Checkpoint process recovery",
                version="1.0.0",
                config={},
                status="published",
            )
        )
        await connection.execute(
            insert(game_sessions).values(
                id=session_id,
                script_id=script_id,
                player_id=None,
                player_character_id="player",
                state={},
                status="in_progress",
            )
        )


async def _checkpoint_counts(db_engine: AsyncEngine, session_id: UUID) -> tuple[int, int]:
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        checkpoint_count = await _table_count(db, session_checkpoints, session_id)
        write_count = await _table_count(db, session_checkpoint_writes, session_id)
    return checkpoint_count, write_count


async def _table_count(db: AsyncSession, table: Table, session_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(table).where(table.c.session_id == session_id)
    )
    return int(result.scalar_one())


async def _remove_script(db_engine: AsyncEngine, script_id: str) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            delete(game_sessions).where(game_sessions.c.script_id == script_id)
        )
        await connection.execute(delete(script_packages).where(script_packages.c.id == script_id))


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"missing required environment variable: {name}")
    return value


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--worker":
        raise SystemExit("usage: test_checkpoint_process_recovery.py --worker <write|restore>")
    asyncio.run(_worker(sys.argv[2]))
