"""为已导入剧本包构建并持久化增量 RAG 索引。"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import RowMapping

from engine.core.package_schema import ScriptPackageImport
from engine.db.protocols import WriteSession
from engine.db.tables import script_knowledge
from engine.rag.chunker import chunk_package
from engine.rag.metadata import json_mapping, metadata_text
from engine.rag.models import (
    EmbeddingProvider,
    RagChunk,
    RagChunkFingerprint,
    RagChunkKey,
    RagIndexingResult,
    RagIndexRecord,
    RagSourceType,
)


class RagIndexRepository(Protocol):
    """剧本包索引流程使用的持久化契约。"""

    async def list_chunk_fingerprints(
        self,
        script_id: str,
    ) -> tuple[RagChunkFingerprint, ...]:
        """返回一个剧本包已存储的分块标识和内容哈希。"""
        ...

    async def apply_incremental_update(
        self,
        script_id: str,
        records: Sequence[RagIndexRecord],
        removed_keys: Sequence[RagChunkKey],
    ) -> None:
        """原子替换已变更分块并删除已移除分块标识。"""
        ...


@dataclass(frozen=True, slots=True)
class RagIndexPlan:
    """描述一次索引更新中已变更、已移除和可复用的部分。"""

    changed_chunks: tuple[RagChunk, ...]
    removed_keys: tuple[RagChunkKey, ...]
    unchanged_count: int


def build_index_records(
    chunks: Sequence[RagChunk],
    embedding_provider: EmbeddingProvider,
) -> tuple[RagIndexRecord, ...]:
    """嵌入分块，并将每个分块与同位置向量配对。"""
    texts = tuple(chunk.text for chunk in chunks)
    embedded = tuple(
        _embedding_vector(vector) for vector in embedding_provider.embed_documents(texts)
    )
    if len(embedded) != len(chunks):
        raise ValueError("embedding provider returned a different number of vectors")
    return tuple(
        RagIndexRecord(chunk=chunk, embedding=embedded[index]) for index, chunk in enumerate(chunks)
    )


async def index_package(
    package: ScriptPackageImport,
    repository: RagIndexRepository,
    embedding_provider: EmbeddingProvider,
) -> RagIndexingResult:
    """应用当前剧本包内容所需的最小索引更新。"""
    script_id = package.package.id
    chunks = chunk_package(package)
    existing = await repository.list_chunk_fingerprints(script_id)
    plan = plan_incremental_index(chunks, existing)
    records = build_index_records(plan.changed_chunks, embedding_provider)
    await repository.apply_incremental_update(script_id, records, plan.removed_keys)
    return RagIndexingResult(
        indexed_records=records,
        unchanged_count=plan.unchanged_count,
        removed_count=len(plan.removed_keys),
    )


def plan_incremental_index(
    chunks: Sequence[RagChunk],
    existing: Sequence[RagChunkFingerprint],
) -> RagIndexPlan:
    """在不调用嵌入器的情况下比较目标分块与持久化哈希。"""
    desired = {chunk_key(chunk): chunk for chunk in chunks}
    desired_hashes = {chunk_key(chunk): _chunk_content_hash(chunk) for chunk in chunks}
    existing_hashes = {fingerprint.key: fingerprint.content_hash for fingerprint in existing}
    removed_keys = tuple(key for key in existing_hashes if key not in desired)
    changed_chunks = tuple(
        chunk for key, chunk in desired.items() if existing_hashes.get(key) != desired_hashes[key]
    )
    unchanged_count = len(desired) - len(changed_chunks)
    return RagIndexPlan(
        changed_chunks=changed_chunks,
        removed_keys=removed_keys,
        unchanged_count=unchanged_count,
    )


def chunk_key(chunk: RagChunk) -> RagChunkKey:
    """返回分块的稳定持久化标识。"""
    return RagChunkKey(
        script_id=chunk.script_id,
        source_type=chunk.source_type,
        source_id=chunk.source_id,
        chunk_index=chunk.chunk_index,
    )


class ScriptKnowledgeIndexRepository:
    """在仅服务端可访问的剧本知识表中持久化 RAG 索引行。"""

    def __init__(self, db: WriteSession) -> None:
        self._db = db

    async def list_chunk_fingerprints(self, script_id: str) -> tuple[RagChunkFingerprint, ...]:
        """加载一个剧本现有的分块键和内容哈希。"""
        result = await self._db.execute(
            select(
                script_knowledge.c.script_id,
                script_knowledge.c.source_type,
                script_knowledge.c.source_id,
                script_knowledge.c.chunk_index,
                script_knowledge.c["metadata"],
            ).where(script_knowledge.c.script_id == script_id),
        )
        if result is None:
            return ()
        return tuple(_fingerprint_from_row(row) for row in result.mappings())

    async def apply_incremental_update(
        self,
        script_id: str,
        records: Sequence[RagIndexRecord],
        removed_keys: Sequence[RagChunkKey],
    ) -> None:
        """提交一次增量删除与插入更新。"""
        removed_and_changed_keys = (*removed_keys, *(chunk_key(record.chunk) for record in records))
        if len(removed_and_changed_keys) == 0:
            return
        await self._delete_chunk_keys(removed_and_changed_keys)
        await self._insert_records(records)
        await self._db.commit()

    async def replace_script_chunks(
        self,
        script_id: str,
        records: Sequence[RagIndexRecord],
    ) -> None:
        """替换属于一个剧本的全部已索引分块。"""
        await self._db.execute(
            delete(script_knowledge).where(script_knowledge.c.script_id == script_id),
        )
        await self._insert_records(records)
        await self._db.commit()

    async def replace_chunks(self, records: Sequence[RagIndexRecord]) -> None:
        """替换记录所表示的每个来源的全部分块。"""
        keys = _source_keys(records)
        for key in keys:
            await self._db.execute(
                delete(script_knowledge).where(
                    script_knowledge.c.script_id == key.script_id,
                    script_knowledge.c.source_type == key.source_type,
                    script_knowledge.c.source_id == key.source_id,
                ),
            )
        await self._insert_records(records)
        await self._db.commit()

    async def _delete_chunk_keys(self, keys: Sequence[RagChunkKey]) -> None:
        for key in keys:
            await self._db.execute(
                delete(script_knowledge).where(
                    script_knowledge.c.script_id == key.script_id,
                    script_knowledge.c.source_type == key.source_type,
                    script_knowledge.c.source_id == key.source_id,
                    script_knowledge.c.chunk_index == key.chunk_index,
                ),
            )

    async def _insert_records(self, records: Sequence[RagIndexRecord]) -> None:
        for record in records:
            await self._db.execute(
                insert(script_knowledge).values(
                    script_id=record.chunk.script_id,
                    source_type=record.chunk.source_type,
                    source_id=record.chunk.source_id,
                    chunk_index=record.chunk.chunk_index,
                    chunk_text=record.chunk.text,
                    embedding=list(record.embedding),
                    metadata=record.chunk.metadata,
                ),
            )


@dataclass(frozen=True, slots=True)
class _SourceKey:
    script_id: str
    source_type: RagSourceType
    source_id: str


def _source_keys(records: Sequence[RagIndexRecord]) -> tuple[_SourceKey, ...]:
    return tuple(
        {
            _SourceKey(record.chunk.script_id, record.chunk.source_type, record.chunk.source_id)
            for record in records
        },
    )


def _embedding_vector(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(float(value) for value in values)


def _chunk_content_hash(chunk: RagChunk) -> str:
    return metadata_text(chunk.metadata, "content_hash")


def _fingerprint_from_row(row: RowMapping) -> RagChunkFingerprint:
    metadata = json_mapping(row.get("metadata"))
    return RagChunkFingerprint(
        key=RagChunkKey(
            script_id=_row_text(row, "script_id"),
            source_type=_row_source_type(row),
            source_id=_row_text(row, "source_id"),
            chunk_index=_row_int(row, "chunk_index"),
        ),
        content_hash=metadata_text(metadata, "content_hash"),
    )


def _row_text(row: RowMapping, key: str) -> str:
    value = row[key]
    if isinstance(value, str):
        return value
    raise TypeError(f"expected text row field: {key}")


def _row_int(row: RowMapping, key: str) -> int:
    value = row[key]
    if isinstance(value, int):
        return value
    raise TypeError(f"expected int row field: {key}")


def _row_source_type(row: RowMapping) -> RagSourceType:
    value = _row_text(row, "source_type")
    match value:
        case "character_knowledge":
            return "character_knowledge"
        case "clue":
            return "clue"
        case "script_context":
            return "script_context"
        case "evidence":
            return "evidence"
        case _:
            raise TypeError(f"expected RAG source type: {value}")
