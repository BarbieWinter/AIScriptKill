from uuid import uuid4

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy.sql import ClauseElement

from engine.api.schemas.common import JsonValue
from engine.core.checkpoint import SupabaseSessionCheckpointSaver

type CheckpointRow = dict[str, str | dict[str, JsonValue] | None]


async def test_supabase_checkpoint_saver_round_trips_langgraph_checkpoint() -> None:
    # Given: a saver backed by the session_checkpoints table contract.
    session = RecordingAsyncSession()
    saver = SupabaseSessionCheckpointSaver(session)
    session_id = str(uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": session_id}}
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"current_stage": "prologue"}

    # When: LangGraph stores and fetches the checkpoint.
    saved_config = await saver.aput(config, checkpoint, {"source": "update"}, {})
    restored = await saver.aget_tuple(saved_config)

    # Then: the same checkpoint payload can rebuild graph state after restart.
    assert restored is not None
    assert restored.config.get("configurable", {}).get("thread_id") == session_id
    assert restored.checkpoint["channel_values"] == {"current_stage": "prologue"}
    assert restored.metadata == {"source": "update"}


class RecordingAsyncSession:
    def __init__(self) -> None:
        self.rows: list[CheckpointRow] = []

    async def execute(self, statement: ClauseElement) -> "RecordingResult":
        table_name = getattr(getattr(statement, "table", None), "name", None)
        if table_name == "session_checkpoints":
            params = statement.compile().params
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
