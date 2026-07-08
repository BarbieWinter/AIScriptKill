from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from sqlalchemy import delete, insert, select
from sqlalchemy.sql import ClauseElement

from engine.core.checkpoint_codec import decode_stored_checkpoint, encode_stored_checkpoint
from engine.db.tables import session_checkpoints


@dataclass(frozen=True, slots=True)
class SupabaseSessionCheckpointSaver(BaseCheckpointSaver[int]):
    db: CheckpointDbSession

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise AsyncCheckpointOnlyError("get_tuple")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        raise AsyncCheckpointOnlyError("list")
        yield

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        raise AsyncCheckpointOnlyError("put")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        raise AsyncCheckpointOnlyError("put_writes")

    def delete_thread(self, thread_id: str) -> None:
        raise AsyncCheckpointOnlyError("delete_thread")

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        locator = checkpoint_locator(config)
        stmt = (
            select(
                session_checkpoints.c.thread_ts,
                session_checkpoints.c.parent_ts,
                session_checkpoints.c.state,
            )
            .where(session_checkpoints.c.session_id == UUID(locator.thread_id))
            .order_by(session_checkpoints.c.created_at.desc())
            .limit(1)
        )
        if locator.checkpoint_id is not None:
            stmt = stmt.where(session_checkpoints.c.thread_ts == locator.checkpoint_id)
        result = await self.db.execute(stmt)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        stored = decode_stored_checkpoint(row["state"])
        return CheckpointTuple(
            config=checkpoint_config(locator.thread_id, str(row["thread_ts"])),
            checkpoint=stored.checkpoint,
            metadata=stored.metadata,
            parent_config=checkpoint_config(locator.thread_id, str(row["parent_ts"]))
            if row["parent_ts"] is not None
            else None,
            pending_writes=stored.pending_writes,
        )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        locator = checkpoint_locator(config or {"configurable": {}})
        stmt = (
            select(
                session_checkpoints.c.thread_ts,
                session_checkpoints.c.parent_ts,
                session_checkpoints.c.state,
            )
            .where(session_checkpoints.c.session_id == UUID(locator.thread_id))
            .order_by(session_checkpoints.c.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        for row in result.mappings().all():
            stored = decode_stored_checkpoint(row["state"])
            yield CheckpointTuple(
                config=checkpoint_config(locator.thread_id, str(row["thread_ts"])),
                checkpoint=stored.checkpoint,
                metadata=stored.metadata,
                parent_config=checkpoint_config(locator.thread_id, str(row["parent_ts"]))
                if row["parent_ts"] is not None
                else None,
                pending_writes=stored.pending_writes,
            )

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        locator = checkpoint_locator(config)
        checkpoint_id = str(checkpoint["id"])
        await self.db.execute(
            insert(session_checkpoints).values(
                session_id=UUID(locator.thread_id),
                thread_ts=checkpoint_id,
                parent_ts=locator.checkpoint_id,
                state=encode_stored_checkpoint(
                    checkpoint=checkpoint,
                    metadata=metadata,
                    pending_writes=[],
                ),
            ),
        )
        return checkpoint_config(locator.thread_id, checkpoint_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        return None

    async def adelete_thread(self, thread_id: str) -> None:
        await self.db.execute(
            delete(session_checkpoints).where(session_checkpoints.c.session_id == UUID(thread_id)),
        )


@dataclass(frozen=True, slots=True)
class CheckpointLocator:
    thread_id: str
    checkpoint_id: str | None


@dataclass(frozen=True, slots=True)
class AsyncCheckpointOnlyError(Exception):
    method: str

    def __str__(self) -> str:
        return f"SupabaseSessionCheckpointSaver.{self.method} requires async LangGraph execution"


def checkpoint_locator(config: RunnableConfig) -> CheckpointLocator:
    configurable = config.get("configurable", {})
    thread_id = configurable.get("thread_id")
    checkpoint_id = configurable.get("checkpoint_id")
    if not isinstance(thread_id, str) or thread_id == "":
        raise CheckpointConfigError("thread_id")
    return CheckpointLocator(
        thread_id=thread_id,
        checkpoint_id=checkpoint_id if isinstance(checkpoint_id, str) else None,
    )


def checkpoint_config(thread_id: str, checkpoint_id: str | None = None) -> RunnableConfig:
    configurable: dict[str, str] = {"thread_id": thread_id}
    if checkpoint_id is not None and checkpoint_id != "":
        configurable["checkpoint_id"] = checkpoint_id
    return {"configurable": configurable}


class CheckpointDbSession(Protocol):
    async def execute(self, statement: ClauseElement) -> CheckpointExecuteResult: ...


class CheckpointExecuteResult(Protocol):
    def mappings(self) -> CheckpointRows: ...


class CheckpointRows(Protocol):
    def one_or_none(self) -> Mapping[str, Any] | None: ...

    def all(self) -> Sequence[Mapping[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class CheckpointConfigError(Exception):
    field: str

    def __str__(self) -> str:
        return f"LangGraph checkpoint config missing {self.field}"
