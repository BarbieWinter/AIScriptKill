import asyncio
from base64 import b64encode
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from langgraph.checkpoint.base import Checkpoint, empty_checkpoint

from engine.core.checkpoint import (
    CheckpointConfigError,
    SupabaseSessionCheckpointSaver,
    checkpoint_config,
)
from engine.core.checkpoint_codec import (
    MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES,
    CheckpointStorageError,
    decode_stored_checkpoint,
    encode_stored_checkpoint,
)
from engine.tests.checkpoint_fakes import (
    ConcurrentGuardCheckpointSession,
    MemoryCheckpointSession,
)


def _checkpoint(checkpoint_id: str, stage: str) -> Checkpoint:
    checkpoint = empty_checkpoint()
    checkpoint["id"] = checkpoint_id
    checkpoint["ts"] = f"2026-07-11T00:00:0{checkpoint_id[-1]}+00:00"
    checkpoint["channel_values"] = {"current_stage": stage}
    return checkpoint


async def test_checkpoint_mutations_commit_on_their_dedicated_session() -> None:
    # 给定：保存器拥有专用数据库会话和一个检查点。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    thread_id = str(uuid4())
    config = checkpoint_config(thread_id)

    # 当：put、待处理写入和删除分别修改存储。
    stored = await saver.aput(config, _checkpoint("0001", "prologue"), {"source": "input"}, {})
    await saver.aput_writes(stored, [("messages", ["hello"])], "task-1")
    await saver.adelete_thread(thread_id)

    # 则：每次修改都建立各自的持久提交边界。
    assert db.commit_count == 3


async def test_checkpoint_put_is_idempotent_for_session_and_checkpoint_id() -> None:
    # 给定：两次重试写入同一个逻辑检查点键。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    thread_id = str(uuid4())
    config = checkpoint_config(thread_id)
    checkpoint = _checkpoint("0001", "prologue")

    # 当：同一个检查点存储两次。
    await saver.aput(config, checkpoint, {"source": "input"}, {})
    await saver.aput(config, checkpoint, {"source": "update"}, {})

    # 则：存储仅包含一条更新后的记录，而不是重复历史记录。
    assert len(db.rows) == 1
    restored = await saver.aget_tuple(checkpoint_config(thread_id, "0001"))
    assert restored is not None
    assert restored.metadata == {"source": "update"}


async def test_pending_writes_round_trip_with_langgraph_retry_semantics() -> None:
    # 给定：已有检查点包含元数据，且没有待处理写入。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    config = checkpoint_config(str(uuid4()))
    stored = await saver.aput(
        config,
        _checkpoint("0001", "prologue"),
        {"source": "loop", "step": 1},
        {},
    )

    # 当：一个任务向同一普通通道写入两次，然后重试第一次写入。
    await saver.aput_writes(
        stored,
        [("messages", ["first"]), ("messages", ["second"])],
        "task-1",
    )
    await saver.aput_writes(stored, [("messages", ["retry-must-not-replace"])], "task-1")
    restored = await saver.aget_tuple(stored)

    # 则：带索引的普通写入可持久化且重试幂等，同时不会丢失元数据。
    assert restored is not None
    assert restored.checkpoint["channel_values"] == {"current_stage": "prologue"}
    assert restored.metadata == {"source": "loop", "step": 1}
    assert restored.pending_writes == [
        ("task-1", "messages", ["first"]),
        ("task-1", "messages", ["second"]),
    ]


async def test_pending_special_write_replaces_same_task_channel() -> None:
    # 给定：已有检查点收到可重试的 LangGraph 错误写入。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    stored = await saver.aput(
        checkpoint_config(str(uuid4())),
        _checkpoint("0001", "prologue"),
        {"source": "loop"},
        {},
    )

    # 当：同一任务重试特殊通道。
    await saver.aput_writes(stored, [("__error__", "first")], "task-1")
    await saver.aput_writes(stored, [("__error__", "replacement")], "task-1")
    restored = await saver.aget_tuple(stored)

    # 则：特殊写入使用 LangGraph 的稳定负数键，并替换先前的值。
    assert restored is not None
    assert restored.pending_writes == [("task-1", "__error__", "replacement")]


async def test_mixed_legacy_and_normalized_writes_keep_persisted_indices() -> None:
    # 给定：旧检查点同时内嵌普通与特殊写入，新表保存相同的规范化记录。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    stored = await saver.aput(
        checkpoint_config(str(uuid4())),
        _checkpoint("0001", "prologue"),
        {"source": "loop"},
        {},
    )
    legacy_writes = [
        ("task-1", "messages", ["normal"]),
        ("task-1", "__error__", "special"),
    ]
    db.rows[0] = replace(
        db.rows[0],
        state=encode_stored_checkpoint(
            checkpoint=_checkpoint("0001", "prologue"),
            metadata={"source": "loop"},
            pending_writes=legacy_writes,
        ),
    )

    # 当：规范化表按负索引优先返回特殊写入，再返回普通索引零写入。
    await saver.aput_writes(
        stored,
        [("messages", ["normal"]), ("__error__", "special")],
        "task-1",
    )
    restored = await saver.aget_tuple(stored)

    # 则：合并使用持久 write_idx 去重，不会按查询顺序把普通写入误判为索引一。
    assert restored is not None
    assert restored.pending_writes == legacy_writes


async def test_pending_writes_arriving_before_checkpoint_survive_saver_restart() -> None:
    # 给定：LangGraph 在异步检查点 put 完成前发出任务写入。
    db = MemoryCheckpointSession()
    first_saver = SupabaseSessionCheckpointSaver(db)
    thread_id = str(uuid4())
    pending_config = checkpoint_config(thread_id, "0001")

    # 当：写入先到达，随后由新保存器 put 匹配的检查点。
    await first_saver.aput_writes(pending_config, [("messages", ["hello"])], "task-1")
    assert db.commit_count == 1
    restarted_saver = SupabaseSessionCheckpointSaver(db)
    await restarted_saver.aput(
        checkpoint_config(thread_id),
        _checkpoint("0001", "prologue"),
        {"source": "input"},
        {},
    )
    restored = await restarted_saver.aget_tuple(pending_config)

    # 则：持久写入记录保留 LangGraph 有效的先写入后 put 顺序。
    assert restored is not None
    assert restored.pending_writes == [("task-1", "messages", ["hello"])]


async def test_distinct_savers_do_not_overwrite_each_others_pending_writes() -> None:
    # 给定：两个保存器实例指向同一个持久检查点。
    db = MemoryCheckpointSession()
    first_saver = SupabaseSessionCheckpointSaver(db)
    second_saver = SupabaseSessionCheckpointSaver(db)
    thread_id = str(uuid4())
    stored = await first_saver.aput(
        checkpoint_config(thread_id),
        _checkpoint("0001", "prologue"),
        {"source": "input"},
        {},
    )

    # 当：两个保存器不共享进程内锁，各自持久化不同的任务写入。
    await asyncio.gather(
        first_saver.aput_writes(stored, [("messages", ["first"])], "task-1"),
        second_saver.aput_writes(stored, [("messages", ["second"])], "task-2"),
    )
    restored = await SupabaseSessionCheckpointSaver(db).aget_tuple(stored)

    # 则：以数据库键区分的记录保留两次写入，而不会在最后一次读改写中丢失数据。
    assert restored is not None
    assert restored.pending_writes == [
        ("task-1", "messages", ["first"]),
        ("task-2", "messages", ["second"]),
    ]


async def test_checkpoint_session_operations_are_serialized() -> None:
    # 给定：记录重叠 SQL 操作的会话替身。
    db = ConcurrentGuardCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    thread_id = str(uuid4())

    # 当：LangGraph 并发调度检查点和写入持久化。
    await asyncio.gather(
        saver.aput(
            checkpoint_config(thread_id),
            _checkpoint("0001", "prologue"),
            {"source": "input"},
            {},
        ),
        saver.aput_writes(
            checkpoint_config(thread_id, "0001"),
            [("messages", ["hello"])],
            "task-1",
        ),
    )
    restored = await saver.aget_tuple(checkpoint_config(thread_id, "0001"))

    # 则：一个专用 AsyncSession 绝不会同时被两个持久化任务使用。
    assert db.max_active_operations == 1
    assert restored is not None
    assert restored.pending_writes == [("task-1", "messages", ["hello"])]


async def test_retrying_an_old_checkpoint_does_not_make_it_latest() -> None:
    # 给定：一个线程已有两个有序检查点。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    base = checkpoint_config(str(uuid4()))
    first = await saver.aput(base, _checkpoint("0001", "prologue"), {"source": "input"}, {})
    await saver.aput(first, _checkpoint("0002", "act1"), {"source": "loop"}, {})

    # 当：延迟重试 upsert 较旧的检查点。
    await saver.aput(base, _checkpoint("0001", "prologue"), {"source": "update"}, {})
    restored = await saver.aget_tuple(base)

    # 则：恢复仍选择单调递增序列中最大的 LangGraph 检查点 ID。
    assert restored is not None
    assert restored.checkpoint["id"] == "0002"


async def test_checkpoint_list_applies_id_before_filter_and_limit() -> None:
    # 给定：三个有序检查点具有不同元数据。
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)
    base = checkpoint_config(str(uuid4()))
    first = await saver.aput(base, _checkpoint("0001", "prologue"), {"source": "input"}, {})
    second = await saver.aput(first, _checkpoint("0002", "act1"), {"source": "loop"}, {})
    third = await saver.aput(second, _checkpoint("0003", "review"), {"source": "loop"}, {})

    # 当：调用方使用精确 ID 和 before/filter/limit 列表契约。
    exact = [item async for item in saver.alist(second)]
    filtered = [
        item
        async for item in saver.alist(
            base,
            filter={"source": "loop"},
            before=third,
            limit=1,
        )
    ]

    # 则：精确 ID 返回一条记录，且仅在元数据过滤后应用 limit。
    assert [item.checkpoint["id"] for item in exact] == ["0002"]
    assert [item.checkpoint["id"] for item in filtered] == ["0002"]


async def test_checkpoint_list_without_thread_is_explicitly_rejected() -> None:
    db = MemoryCheckpointSession()
    saver = SupabaseSessionCheckpointSaver(db)

    with pytest.raises(CheckpointConfigError):
        _ = [item async for item in saver.alist(None)]


async def test_malformed_pending_write_raises_storage_error_through_context_manager() -> None:
    # 给定：已存储检查点的待处理写入列表包含无类型标量。
    raw = encode_stored_checkpoint(
        checkpoint=_checkpoint("0001", "prologue"),
        metadata={"source": "input"},
        pending_writes=[],
    )
    raw["pending_writes"] = ["malformed"]

    # 当/则：解码传播类型化错误，而不会触发冻结异常失败。
    with pytest.raises(CheckpointStorageError):
        with _passthrough_context():
            decode_stored_checkpoint(raw)


def test_checkpoint_schema_has_unique_session_thread_key() -> None:
    # 给定：所有数据库迁移均已应用到运行时检查点表。
    migrations = Path("supabase/migrations").glob("*.sql")
    sql = "\n".join(path.read_text(encoding="utf-8") for path in migrations)
    normalized = " ".join(sql.split()).lower()

    # 则：数据库唯一性与保存器的 upsert 冲突键一致。
    cleanup_position = normalized.find("delete from public.session_checkpoints")
    unique_position = normalized.find("create unique index")
    assert cleanup_position >= 0
    assert cleanup_position < unique_position
    assert "row_number() over" in normalized
    assert "unique index" in normalized
    assert "session_checkpoints(session_id, thread_ts)" in normalized
    assert "create table public.session_checkpoint_writes" in normalized
    assert "primary key (session_id, checkpoint_id, task_id, write_idx)" in normalized


@pytest.mark.parametrize(
    "mutation",
    [
        {"version": 2},
        {
            "pending_writes": [
                {"type": "json", "payload": b64encode(b"{").decode("ascii")},
            ],
        },
    ],
)
def test_checkpoint_codec_rejects_incompatible_or_corrupt_storage(
    mutation: dict[str, Any],
) -> None:
    raw = encode_stored_checkpoint(
        checkpoint=_checkpoint("0001", "prologue"),
        metadata={"source": "input"},
        pending_writes=[],
    )
    raw.update(mutation)

    with pytest.raises(CheckpointStorageError):
        decode_stored_checkpoint(raw)


def test_checkpoint_codec_rejects_oversized_typed_payload_before_decode() -> None:
    # 给定：数据库记录声明了超过解码预算的有效 base64 载荷。
    raw = encode_stored_checkpoint(
        checkpoint=_checkpoint("0001", "prologue"),
        metadata={"source": "input"},
        pending_writes=[],
    )
    raw["metadata"] = {
        "type": "bytes",
        "payload": b64encode(b"x" * (MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES + 1)).decode("ascii"),
    }

    # 当/则：编解码器在把攻击者控制的字节交给 serde 前失败。
    with pytest.raises(CheckpointStorageError) as exc_info:
        decode_stored_checkpoint(raw)

    assert exc_info.value.field == "typed_payload_limit"


@contextmanager
def _passthrough_context() -> Any:
    yield
