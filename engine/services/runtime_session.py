"""协调生产 REST 请求、LangGraph 检查点和会话投影。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from engine.agents.npc_agent import create_npc_responder
from engine.api.errors import bad_request, not_found
from engine.api.schemas import ActionRequest, ActionResponse
from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.checkpoint_models import checkpoint_config, checkpoint_locator
from engine.core.game_state import GameState
from engine.core.script_engine import ScriptEngine
from engine.core.script_engine_errors import ScriptEngineActionError
from engine.db.session import SessionFactory
from engine.rag.provider_factory import create_embedding_provider
from engine.rag.retriever import RagRetriever, ScriptKnowledgeSearchRepository
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.repositories.session_models import StoredSession
from engine.repositories.session_repository import SessionRepository
from engine.services.runtime_action_mappers import (
    runtime_action_input,
    runtime_action_result,
)
from engine.services.runtime_state_mappers import (
    initial_game_state,
    project_runtime_state,
    synchronize_monotonic_progress,
)


class RuntimeActionExecutor(Protocol):
    async def execute(
        self,
        session: StoredSession,
        payload: ActionRequest,
        request_db: AsyncSession,
    ) -> ActionResponse: ...


@dataclass(frozen=True, slots=True)
class RuntimeActionExecution:
    response: ActionResponse
    final_state: GameState
    checkpoint_id: str | None


@dataclass(frozen=True, slots=True)
class LangGraphRuntimeActionExecutor:
    """使用独立检查点会话执行并投影一个真实图动作。"""

    async def execute(
        self,
        session: StoredSession,
        payload: ActionRequest,
        request_db: AsyncSession,
    ) -> ActionResponse:
        async with session_action_lock(session.id):
            execution = await self.execute_locked(session, payload, request_db)
            await request_db.commit()
            return execution.response

    async def prepare_command_base_locked(
        self,
        session: StoredSession,
        request_db: AsyncSession,
    ) -> tuple[GameState, str | None]:
        """Capture the exact private state and checkpoint anchor used by a new command."""

        package = await get_runtime_package(request_db, session.script_id)
        if package is None:
            raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到会话对应的已发布剧本包")
        async with SessionFactory() as checkpoint_db:
            engine = ScriptEngine.from_package(
                package,
                checkpointer=SupabaseSessionCheckpointSaver(checkpoint_db),
            )
            inspection = await engine.inspect_state(checkpoint_config(str(session.id)))
        previous = inspection.state or initial_game_state(session)
        previous = synchronize_monotonic_progress(previous, session.state)
        return previous, checkpoint_locator(inspection.config).checkpoint_id

    async def execute_locked(
        self,
        session: StoredSession,
        payload: ActionRequest,
        request_db: AsyncSession,
        *,
        command_id: UUID | None = None,
        command_attempt: int | None = None,
        base_state: GameState | None = None,
        base_checkpoint_id: str | None = None,
    ) -> RuntimeActionExecution:
        """Execute or recover one action while the caller owns the session lock."""

        repository = SessionRepository(request_db)
        latest = await repository.get_session(session.id)
        if latest is None:
            raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
        package = await get_runtime_package(request_db, latest.script_id)
        if package is None:
            raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到会话对应的已发布剧本包")
        if (command_id is None) != (command_attempt is None):
            raise ValueError("command_id and command_attempt must be provided together")

        async with SessionFactory() as checkpoint_db:
            retriever = RagRetriever(
                create_embedding_provider(),
                ScriptKnowledgeSearchRepository(request_db),
            )
            saver = SupabaseSessionCheckpointSaver(checkpoint_db)
            engine = ScriptEngine.from_package(
                package,
                checkpointer=saver,
                npc_responder=create_npc_responder(retriever),
            )
            if command_id is None or command_attempt is None:
                restored = await engine.restore_state(thread_id=str(latest.id))
                previous = restored or initial_game_state(latest)
                previous = synchronize_monotonic_progress(previous, latest.state)
                action = runtime_action_input(payload)
                try:
                    current = await engine.run_action(
                        previous,
                        action_id=action.action_id,
                        target=action.target,
                        text=action.text,
                        thread_id=str(latest.id),
                    )
                except ScriptEngineActionError as exc:
                    raise bad_request(exc.code, exc.message) from exc
                final_checkpoint_id = None
            else:
                latest_command = await saver.aget_latest_command_checkpoint(
                    thread_id=str(latest.id),
                    command_id=command_id,
                    max_attempt=command_attempt,
                )
                if latest_command is None:
                    if base_state is None:
                        raise RuntimeError("durable command base state is unavailable")
                    previous = base_state
                    action = runtime_action_input(payload)
                    config = checkpoint_config(
                        str(latest.id),
                        base_checkpoint_id,
                        command_id=command_id,
                        command_attempt=command_attempt,
                    )
                    try:
                        current, final_config = await engine.run_action_from(
                            previous,
                            action_id=action.action_id,
                            target=action.target,
                            text=action.text,
                            config=config,
                        )
                    except ScriptEngineActionError as exc:
                        raise bad_request(exc.code, exc.message) from exc
                    final_checkpoint_id = checkpoint_locator(final_config).checkpoint_id
                else:
                    predecessor = checkpoint_locator(latest_command.config)
                    exact_config = checkpoint_config(
                        str(latest.id),
                        predecessor.checkpoint_id,
                        command_id=command_id,
                        command_attempt=command_attempt,
                    )
                    inspection = await engine.inspect_state(exact_config)
                    if inspection.state is None:
                        raise RuntimeError("durable command checkpoint state is unavailable")
                    current = inspection.state
                    final_config = inspection.config
                    if not inspection.quiescent:
                        current, final_config = await engine.resume_action(exact_config)
                    final_checkpoint_id = checkpoint_locator(final_config).checkpoint_id
                    if base_state is None:
                        raise RuntimeError("durable command base state is unavailable")
                    previous = base_state

        stage_name = engine.runtime.stage_by_id(current["current_stage"]).name
        projection = project_runtime_state(current, latest.state, stage_name=stage_name)
        response, effect = runtime_action_result(payload, previous, current, package)
        await repository.project_runtime_action_no_commit(latest, projection, effect)
        return RuntimeActionExecution(
            response=response,
            final_state=current,
            checkpoint_id=final_checkpoint_id,
        )


@asynccontextmanager
async def session_action_lock(session_id: UUID) -> AsyncGenerator[None]:
    """用事务级 PostgreSQL advisory lock 串行化跨进程同会话动作。"""

    async with SessionFactory() as lock_db:
        try:
            await lock_db.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(str(session_id), 0)))
            )
            yield
            await lock_db.commit()
        except BaseException:
            await lock_db.rollback()
            raise


def create_runtime_action_executor() -> RuntimeActionExecutor:
    """返回默认的生产 LangGraph 执行器。"""

    return LangGraphRuntimeActionExecutor()
