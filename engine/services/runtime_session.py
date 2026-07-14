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
class LangGraphRuntimeActionExecutor:
    """使用独立检查点会话执行并投影一个真实图动作。"""

    async def execute(
        self,
        session: StoredSession,
        payload: ActionRequest,
        request_db: AsyncSession,
    ) -> ActionResponse:
        repository = SessionRepository(request_db)
        async with _session_action_lock(session.id):
            latest = await repository.get_session(session.id)
            if latest is None:
                raise not_found("SESSION_NOT_FOUND", "未找到指定游戏会话")
            package = await get_runtime_package(request_db, latest.script_id)
            if package is None:
                raise not_found("SCRIPT_PACKAGE_NOT_FOUND", "未找到会话对应的已发布剧本包")

            async with SessionFactory() as checkpoint_db:
                retriever = RagRetriever(
                    create_embedding_provider(),
                    ScriptKnowledgeSearchRepository(request_db),
                )
                engine = ScriptEngine.from_package(
                    package,
                    checkpointer=SupabaseSessionCheckpointSaver(checkpoint_db),
                    npc_responder=create_npc_responder(retriever),
                )
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

            stage_name = engine.runtime.stage_by_id(current["current_stage"]).name
            projection = project_runtime_state(
                current,
                latest.state,
                stage_name=stage_name,
            )
            response, effect = runtime_action_result(payload, previous, current, package)
            await repository.project_runtime_action(latest, projection, effect)
            return response


@asynccontextmanager
async def _session_action_lock(session_id: UUID) -> AsyncGenerator[None]:
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
