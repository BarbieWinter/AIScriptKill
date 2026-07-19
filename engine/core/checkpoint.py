"""在 PostgreSQL 中持久化 LangGraph 检查点和待处理写入。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
)
from langgraph.checkpoint.serde.base import SerializerProtocol
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.schemas.common import JsonValue
from engine.core.checkpoint_codec import (
    ENCODING_VERSION,
    MAX_CHECKPOINT_PENDING_WRITES,
    STRICT_CHECKPOINT_SERDE,
    CheckpointStorageError,
    decode_stored_checkpoint,
    decode_typed,
    encode_stored_checkpoint,
    encode_typed,
)
from engine.core.checkpoint_models import (
    AsyncCheckpointOnlyError,
    CheckpointAttemptFencedError,
    CheckpointConfigError,
    CheckpointDbSession,
    CheckpointLocator,
    checkpoint_config,
    checkpoint_locator,
)
from engine.db.tables import (
    session_checkpoint_writes,
    session_checkpoints,
    session_command_receipts,
)

type IndexedPendingWrite = tuple[int, PendingWrite]


@dataclass(frozen=True, slots=True)
class SupabaseSessionCheckpointSaver(BaseCheckpointSaver[int]):
    """通过一个专用数据库会话串行化 LangGraph 持久化。

    提供的会话不得与请求事务共享：LangGraph 会并发调度检查点和待处理写入调用，
    因此本保存器需要保护不可并发使用的 ``AsyncSession``。待处理写入使用独立数据库行，
    以持久保留先写入后检查点的顺序，并支持不同保存器进程。数据库变更各自建立提交边界。
    列表查询必须提供线程配置，因为跨会话历史不在支持范围内。
    """

    db: AsyncSession | CheckpointDbSession
    lease_seconds: int = 30
    serde: SerializerProtocol = field(
        default=STRICT_CHECKPOINT_SERDE,
        init=False,
        repr=False,
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.lease_seconds) is not int or self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be a positive integer")

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """拒绝同步读取，因为本保存器持有异步数据库会话。"""

        raise AsyncCheckpointOnlyError("get_tuple")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        """拒绝同步列表查询，因为本保存器持有异步数据库会话。"""

        raise AsyncCheckpointOnlyError("list")
        yield

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """拒绝在纯异步保存器上同步写入检查点。"""

        raise AsyncCheckpointOnlyError("put")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """拒绝在纯异步保存器上同步写入待处理数据。"""

        raise AsyncCheckpointOnlyError("put_writes")

    def delete_thread(self, thread_id: str) -> None:
        """拒绝在纯异步保存器上同步删除。"""

        raise AsyncCheckpointOnlyError("delete_thread")

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """加载一个检查点及其持久待处理写入，然后关闭读取事务。"""

        async with self._lock:
            try:
                return await self._aget_tuple(config)
            finally:
                await self.db.rollback()

    async def alatest_command_config(
        self,
        thread_id: str,
        command_id: UUID | str,
        command_attempt: int,
    ) -> RunnableConfig | None:
        """返回指定命令尝试中最大 checkpoint_id 的精确配置。"""

        item = await self.aget_tuple(
            checkpoint_config(
                thread_id,
                command_id=str(command_id),
                command_attempt=command_attempt,
            )
        )
        return item.config if item is not None else None

    async def alatest_command_config_through_attempt(
        self,
        thread_id: str,
        command_id: UUID | str,
        max_attempt: int,
    ) -> RunnableConfig | None:
        """跨同一命令不晚于 max_attempt 的尝试返回最大 checkpoint_id。"""

        base = checkpoint_config(
            thread_id,
            command_id=str(command_id),
            command_attempt=max_attempt,
        )
        locator = checkpoint_locator(base)
        async with self._lock:
            try:
                result = await self.db.execute(
                    select(session_checkpoints.c.thread_ts)
                    .where(
                        session_checkpoints.c.session_id == UUID(locator.thread_id),
                        session_checkpoints.c.command_id == UUID(cast(str, locator.command_id)),
                        session_checkpoints.c.command_attempt <= max_attempt,
                        session_checkpoints.c.state.contains({"version": ENCODING_VERSION}),
                    )
                    .order_by(
                        session_checkpoints.c.thread_ts.desc(),
                        session_checkpoints.c.created_at.desc(),
                    )
                    .limit(1)
                )
                row = result.mappings().one_or_none()
            finally:
                await self.db.rollback()
        if row is None:
            return None
        return checkpoint_config(
            locator.thread_id,
            str(row["thread_ts"]),
            command_id=locator.command_id,
            command_attempt=max_attempt,
        )

    async def aget_latest_command_checkpoint(
        self,
        *,
        thread_id: str,
        command_id: UUID | str,
        command_attempt: int | None = None,
        max_attempt: int | None = None,
    ) -> CheckpointTuple | None:
        """加载精确尝试或截至 max_attempt 的最大 checkpoint_id。"""

        if (command_attempt is None) == (max_attempt is None):
            raise CheckpointConfigError("command_attempt")
        if max_attempt is not None:
            exact = await self.alatest_command_config_through_attempt(
                thread_id,
                command_id,
                max_attempt,
            )
            return await self.aget_tuple(exact) if exact is not None else None
        return await self.aget_tuple(
            checkpoint_config(
                thread_id,
                command_id=str(command_id),
                command_attempt=command_attempt,
            )
        )

    async def _aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        locator = checkpoint_locator(config)
        stmt = (
            select(
                session_checkpoints.c.thread_ts,
                session_checkpoints.c.parent_ts,
                session_checkpoints.c.state,
            )
            .where(session_checkpoints.c.session_id == UUID(locator.thread_id))
            .where(session_checkpoints.c.state.contains({"version": ENCODING_VERSION}))
            .order_by(
                # LangGraph 将最大 checkpoint_id 定义为最新检查点；并发提交的完成顺序可能不同，
                # 因此不能使用数据库插入时间决定这里的排序。
                session_checkpoints.c.thread_ts.desc(),
                session_checkpoints.c.created_at.desc(),
            )
            .limit(1)
        )
        if locator.checkpoint_id is not None:
            stmt = stmt.where(session_checkpoints.c.thread_ts == locator.checkpoint_id)
        if locator.command_id is not None and locator.command_attempt is not None:
            stmt = stmt.where(session_checkpoints.c.command_id == UUID(locator.command_id))
            if locator.checkpoint_id is None:
                stmt = stmt.where(
                    session_checkpoints.c.command_attempt == locator.command_attempt,
                )
            else:
                # 精确恢复可以读取同一命令的前序尝试，但绝不能跨命令或读取未来尝试。
                # 返回配置仍携带当前尝试，后续写入会被 receipt 围栏并标记为当前代。
                stmt = stmt.where(
                    session_checkpoints.c.command_attempt <= locator.command_attempt,
                )
        result = await self.db.execute(stmt)
        row = result.mappings().one_or_none()
        if row is None:
            return None
        stored = decode_stored_checkpoint(row["state"])
        checkpoint_id = str(row["thread_ts"])
        normalized_writes = await self._aload_pending_writes(
            locator.thread_id,
            (checkpoint_id,),
        )
        return CheckpointTuple(
            config=_located_checkpoint_config(locator, checkpoint_id),
            checkpoint=stored.checkpoint,
            metadata=stored.metadata,
            parent_config=_located_checkpoint_config(locator, str(row["parent_ts"]))
            if row["parent_ts"] is not None
            else None,
            pending_writes=_merge_pending_write_records(
                stored.pending_writes,
                normalized_writes.get(checkpoint_id, ()),
            ),
        )

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """按从新到旧列出筛选后的线程历史，并规范化待处理写入。"""

        if config is None:
            raise CheckpointConfigError("thread_id")
        locator = checkpoint_locator(config)
        before_locator = checkpoint_locator(before) if before is not None else None
        if before_locator is not None and before_locator.thread_id != locator.thread_id:
            raise CheckpointConfigError("before.thread_id")
        selected: list[
            tuple[
                str,
                str | None,
                Checkpoint,
                CheckpointMetadata,
                list[PendingWrite],
            ]
        ] = []
        async with self._lock:
            try:
                stmt = (
                    select(
                        session_checkpoints.c.thread_ts,
                        session_checkpoints.c.parent_ts,
                        session_checkpoints.c.state,
                    )
                    .where(session_checkpoints.c.session_id == UUID(locator.thread_id))
                    .where(session_checkpoints.c.state.contains({"version": ENCODING_VERSION}))
                    .order_by(
                        session_checkpoints.c.thread_ts.desc(),
                        session_checkpoints.c.created_at.desc(),
                    )
                )
                if locator.command_id is not None and locator.command_attempt is not None:
                    stmt = stmt.where(
                        session_checkpoints.c.command_id == UUID(locator.command_id),
                        session_checkpoints.c.command_attempt == locator.command_attempt,
                    )
                result = await self.db.execute(stmt)
                for row in result.mappings().all():
                    checkpoint_id = str(row["thread_ts"])
                    if locator.checkpoint_id is not None and checkpoint_id != locator.checkpoint_id:
                        continue
                    if (
                        before_locator is not None
                        and before_locator.checkpoint_id is not None
                        and checkpoint_id >= before_locator.checkpoint_id
                    ):
                        continue
                    stored = decode_stored_checkpoint(row["state"])
                    if filter is not None and not all(
                        stored.metadata.get(key) == value for key, value in filter.items()
                    ):
                        continue
                    if limit is not None and len(selected) >= max(limit, 0):
                        break
                    selected.append(
                        (
                            checkpoint_id,
                            str(row["parent_ts"]) if row["parent_ts"] is not None else None,
                            stored.checkpoint,
                            stored.metadata,
                            stored.pending_writes,
                        )
                    )
                normalized_writes = await self._aload_pending_writes(
                    locator.thread_id,
                    tuple(item[0] for item in selected),
                )
            finally:
                await self.db.rollback()
        items = [
            CheckpointTuple(
                config=_located_checkpoint_config(locator, checkpoint_id),
                checkpoint=checkpoint,
                metadata=metadata,
                parent_config=_located_checkpoint_config(locator, parent_id)
                if parent_id is not None
                else None,
                pending_writes=_merge_pending_write_records(
                    legacy_writes,
                    normalized_writes.get(checkpoint_id, ()),
                ),
            )
            for checkpoint_id, parent_id, checkpoint, metadata, legacy_writes in selected
        ]
        for item in items:
            yield item

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """更新插入并提交一个已编码检查点，同时保留更早写入。"""

        _ = new_versions
        locator = checkpoint_locator(config)
        checkpoint_id = str(checkpoint["id"])
        async with self._lock:
            try:
                await self._renew_command_lease(locator)
                legacy_writes = await self._aload_legacy_pending_writes(
                    locator.thread_id,
                    checkpoint_id,
                )
                stored_state = encode_stored_checkpoint(
                    checkpoint=checkpoint,
                    metadata=metadata,
                    pending_writes=legacy_writes,
                )
                statement = insert(session_checkpoints).values(
                    session_id=UUID(locator.thread_id),
                    thread_ts=checkpoint_id,
                    parent_ts=locator.checkpoint_id,
                    state=stored_state,
                    command_id=UUID(locator.command_id) if locator.command_id is not None else None,
                    command_attempt=locator.command_attempt,
                )
                await self.db.execute(
                    statement.on_conflict_do_update(
                        index_elements=(
                            session_checkpoints.c.session_id,
                            session_checkpoints.c.thread_ts,
                        ),
                        set_={
                            "parent_ts": locator.checkpoint_id,
                            "state": stored_state,
                            "command_id": (
                                UUID(locator.command_id) if locator.command_id is not None else None
                            ),
                            "command_attempt": locator.command_attempt,
                        },
                    ),
                )
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise
        return _located_checkpoint_config(locator, checkpoint_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        """持久化并提交幂等任务写入，即使检查点尚未插入。"""

        _ = task_path
        locator = checkpoint_locator(config)
        if locator.checkpoint_id is None:
            raise CheckpointConfigError("checkpoint_id")
        if len(writes) == 0 and locator.command_id is None:
            return
        records = [
            {
                "session_id": UUID(locator.thread_id),
                "checkpoint_id": locator.checkpoint_id,
                "task_id": task_id,
                "write_idx": WRITES_IDX_MAP.get(channel, index),
                "channel": channel,
                "value": encode_typed(value),
            }
            for index, (channel, value) in enumerate(writes)
        ]
        async with self._lock:
            try:
                await self._renew_command_lease(locator)
                if records:
                    statement = insert(session_checkpoint_writes).values(records)
                    await self.db.execute(
                        statement.on_conflict_do_update(
                            index_elements=(
                                session_checkpoint_writes.c.session_id,
                                session_checkpoint_writes.c.checkpoint_id,
                                session_checkpoint_writes.c.task_id,
                                session_checkpoint_writes.c.write_idx,
                            ),
                            set_={
                                "channel": statement.excluded.channel,
                                "value": statement.excluded.value,
                            },
                            where=statement.excluded.write_idx < 0,
                        ),
                    )
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise

    async def _renew_command_lease(self, locator: CheckpointLocator) -> None:
        if locator.command_id is None or locator.command_attempt is None:
            return
        result = await self.db.execute(
            update(session_command_receipts)
            .where(
                session_command_receipts.c.session_id == UUID(locator.thread_id),
                session_command_receipts.c.command_id == UUID(locator.command_id),
                session_command_receipts.c.status == "processing",
                session_command_receipts.c.attempt_count == locator.command_attempt,
            )
            .values(
                lease_expires_at=func.now() + timedelta(seconds=self.lease_seconds),
                updated_at=func.now(),
            )
            .returning(session_command_receipts.c.command_id)
        )
        if result.mappings().one_or_none() is None:
            raise CheckpointAttemptFencedError(
                locator.thread_id,
                locator.command_id,
                locator.command_attempt,
            )

    async def _aload_pending_writes(
        self,
        thread_id: str,
        checkpoint_ids: Sequence[str],
    ) -> dict[str, list[IndexedPendingWrite]]:
        if len(checkpoint_ids) == 0:
            return {}
        result = await self.db.execute(
            select(
                session_checkpoint_writes.c.checkpoint_id,
                session_checkpoint_writes.c.task_id,
                session_checkpoint_writes.c.write_idx,
                session_checkpoint_writes.c.channel,
                session_checkpoint_writes.c.value,
            )
            .where(session_checkpoint_writes.c.session_id == UUID(thread_id))
            .where(session_checkpoint_writes.c.checkpoint_id.in_(checkpoint_ids))
            .order_by(
                session_checkpoint_writes.c.checkpoint_id,
                session_checkpoint_writes.c.task_id,
                session_checkpoint_writes.c.write_idx,
            ),
        )
        grouped: dict[str, list[IndexedPendingWrite]] = {}
        for row in result.mappings().all():
            checkpoint_id = row["checkpoint_id"]
            task_id = row["task_id"]
            write_idx = row["write_idx"]
            channel = row["channel"]
            value = row["value"]
            if (
                not isinstance(checkpoint_id, str)
                or not isinstance(task_id, str)
                or type(write_idx) is not int
                or not isinstance(channel, str)
            ):
                raise CheckpointStorageError("pending_write_row")
            if not isinstance(value, dict):
                raise CheckpointStorageError("pending_write_row")
            value_mapping = cast(dict[object, object], value)
            type_name = value_mapping.get("type")
            payload = value_mapping.get("payload")
            if not isinstance(type_name, str) or not isinstance(payload, str):
                raise CheckpointStorageError("pending_write_row")
            typed_value: dict[str, JsonValue] = {"type": type_name, "payload": payload}
            pending = grouped.setdefault(checkpoint_id, [])
            if len(pending) >= MAX_CHECKPOINT_PENDING_WRITES:
                raise CheckpointStorageError("pending_writes_limit")
            pending.append((write_idx, (task_id, channel, decode_typed(typed_value))))
        return grouped

    async def _aload_legacy_pending_writes(
        self,
        thread_id: str,
        checkpoint_id: str,
    ) -> list[PendingWrite]:
        result = await self.db.execute(
            select(session_checkpoints.c.state)
            .where(session_checkpoints.c.session_id == UUID(thread_id))
            .where(session_checkpoints.c.thread_ts == checkpoint_id)
            .limit(1),
        )
        row = result.mappings().one_or_none()
        if row is None:
            return []
        return decode_stored_checkpoint(row["state"]).pending_writes

    async def adelete_thread(self, thread_id: str) -> None:
        """原子删除一个线程的规范化写入和检查点。"""

        async with self._lock:
            try:
                await self.db.execute(
                    delete(session_checkpoint_writes).where(
                        session_checkpoint_writes.c.session_id == UUID(thread_id)
                    ),
                )
                await self.db.execute(
                    delete(session_checkpoints).where(
                        session_checkpoints.c.session_id == UUID(thread_id)
                    ),
                )
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise


def _located_checkpoint_config(locator: CheckpointLocator, checkpoint_id: str) -> RunnableConfig:
    return checkpoint_config(
        locator.thread_id,
        checkpoint_id,
        command_id=locator.command_id,
        command_attempt=locator.command_attempt,
    )


def _merge_pending_write_records(
    existing: Sequence[PendingWrite],
    additions: Sequence[IndexedPendingWrite],
) -> list[PendingWrite]:
    indexed: dict[tuple[str, int], PendingWrite] = {}
    task_offsets: dict[str, int] = {}
    for write in existing:
        existing_task_id, channel, _ = write
        index = task_offsets.get(existing_task_id, 0)
        task_offsets[existing_task_id] = index + 1
        indexed[(existing_task_id, WRITES_IDX_MAP.get(channel, index))] = write
    for write_idx, write in additions:
        addition_task_id, channel, _ = write
        expected_write_idx = WRITES_IDX_MAP.get(channel, write_idx)
        if expected_write_idx != write_idx:
            raise CheckpointStorageError("pending_write_index")
        key = (addition_task_id, write_idx)
        if key[1] >= 0 and key in indexed:
            continue
        indexed[key] = write
    return list(indexed.values())
