from collections.abc import Sequence
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from engine.rag.models import (
    EmbeddingProvider,
    EmbeddingVector,
    RagIndexRecord,
    RagSessionContext,
    RetrievedChunk,
)
from engine.rag.permissions import is_chunk_visible
from engine.rag.reranker import rerank
from engine.rag.scoring import embedding_vector, rescore_with_bm25, score_records
from engine.rag.sql import build_retrieval_sql, row_to_result, vector_literal


class RagSearchRepository(Protocol):
    async def search(
        self,
        query: str,
        query_embedding: EmbeddingVector,
        context: RagSessionContext,
        limit: int,
    ) -> tuple[RetrievedChunk, ...]: ...


class RagRetriever:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        repository: RagSearchRepository,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._repository = repository

    async def retrieve(
        self,
        query: str,
        session_context: RagSessionContext,
        limit: int = 5,
    ) -> list[RetrievedChunk]:
        cleaned_query = query.strip()
        if not cleaned_query or limit <= 0:
            return []
        query_embedding = embedding_vector(self._embedding_provider.embed_query(cleaned_query))
        results = await self._repository.search(
            cleaned_query,
            query_embedding,
            session_context,
            limit,
        )
        return list(results)


class InMemoryRagRepository:
    def __init__(self, records: Sequence[RagIndexRecord]) -> None:
        self._records = tuple(records)

    async def search(
        self,
        query: str,
        query_embedding: EmbeddingVector,
        context: RagSessionContext,
        limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        allowed_records = tuple(
            record for record in self._records if is_chunk_visible(record.chunk, context)
        )
        ranked = score_records(query, query_embedding, allowed_records)
        return rerank(ranked)[:limit]


class ScriptKnowledgeSearchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def search(
        self,
        query: str,
        query_embedding: EmbeddingVector,
        context: RagSessionContext,
        limit: int,
    ) -> tuple[RetrievedChunk, ...]:
        result = await self._db.execute(
            build_retrieval_sql(),
            {
                "query": query,
                "query_embedding": vector_literal(query_embedding),
                "script_id": context.script_id,
                "current_stage_order": context.current_stage_order,
                "viewer_character_id": context.viewer_character_id,
                "speaker_character_id": context.speaker_character_id,
                "is_dm": context.is_dm,
                "unlocked_clue_ids": list(context.unlocked_clue_ids),
                "limit": _candidate_limit(limit),
            },
        )
        candidates = tuple(row_to_result(row) for row in result.mappings())
        return rerank(rescore_with_bm25(query, candidates))[:limit]


def _candidate_limit(limit: int) -> int:
    return max(limit * 4, 20)
