from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy.sql import ClauseElement, Executable

from engine.api.schemas.common import JsonValue
from engine.core.checkpoint import SupabaseSessionCheckpointSaver

type CheckpointRow = dict[str, str | dict[str, JsonValue] | None]


async def test_supabase_checkpoint_saver_round_trips_langgraph_checkpoint() -> None:
    # 给定：由 session_checkpoints 表契约支持的保存器。
    session = RecordingAsyncSession()
    saver = SupabaseSessionCheckpointSaver(session)
    session_id = str(uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": session_id}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"current_stage": "prologue"}

    # 当：LangGraph 存储并获取检查点。
    saved_config = await saver.aput(config, checkpoint, {"source": "update"}, {})
    restored = await saver.aget_tuple(saved_config)

    # 则：同一检查点载荷可以在重启后重建图状态。
    assert restored is not None
    assert restored.config.get("configurable", {}).get("thread_id") == session_id
    assert restored.checkpoint["channel_values"] == {"current_stage": "prologue"}
    assert restored.metadata == {"source": "update"}


class RecordingAsyncSession:
    def __init__(self) -> None:
        self.rows: list[CheckpointRow] = []
        self.commit_count = 0

    async def execute(self, statement: Executable) -> "RecordingResult":
        if not isinstance(statement, ClauseElement):
            raise AssertionError("checkpoint fake only accepts SQL clause statements")
        compiled = statement.compile()
        if "session_checkpoint_writes" in compiled.string:
            return RecordingResult([])
        table_name = getattr(getattr(statement, "table", None), "name", None)
        if table_name == "session_checkpoints":
            params = compiled.params
            thread_ts = params.get("thread_ts") if isinstance(params, dict) else None
            parent_ts = params.get("parent_ts") if isinstance(params, dict) else None
            state = params.get("state") if isinstance(params, dict) else None
            if not isinstance(thread_ts, str) or not isinstance(state, dict):
                return RecordingResult(self.rows)
            self.rows.append(
                {
                    "thread_ts": thread_ts,
                    "parent_ts": str(parent_ts) if parent_ts is not None else None,
                    "state": state,
                },
            )
        return RecordingResult(self.rows)

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        pass


class RecordingResult:
    def __init__(self, rows: list[CheckpointRow]) -> None:
        self._rows = rows

    def mappings(self) -> "RecordingResult":
        return self

    def one_or_none(self) -> CheckpointRow | None:
        if len(self._rows) == 0:
            return None
        return self._rows[-1]

    def all(self) -> list[CheckpointRow]:
        return list(reversed(self._rows))
