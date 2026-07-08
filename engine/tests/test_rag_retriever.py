from collections.abc import Sequence
from time import perf_counter

from engine.rag.chunker import chunk_package
from engine.rag.embeddings import DeterministicEmbeddingProvider
from engine.rag.indexer import build_index_records
from engine.rag.models import RagChunk, RagIndexRecord, RagSessionContext
from engine.rag.retriever import InMemoryRagRepository, RagRetriever, build_retrieval_sql
from engine.tests.rag_fixtures import rag_package


async def test_retrieve_truth_visible_to_dm_but_not_npc() -> None:
    retriever = _rag_retriever()

    dm_results = await retriever.retrieve(
        "凶手是谁",
        RagSessionContext(
            script_id="minimal-case",
            current_stage="prologue",
            current_stage_order=0,
            character_id="dm",
            is_dm=True,
        ),
    )
    npc_results = await retriever.retrieve(
        "凶手是谁",
        RagSessionContext(
            script_id="minimal-case",
            current_stage="prologue",
            current_stage_order=0,
            character_id="npc",
        ),
    )

    assert any("NPC角色是凶手" in result.chunk.text for result in dm_results)
    assert all("NPC角色是凶手" not in result.chunk.text for result in npc_results)


async def test_retrieve_keeps_locked_clues_out_of_player_results() -> None:
    retriever = _rag_retriever()

    locked_results = await retriever.retrieve(
        "线索一",
        RagSessionContext(
            script_id="minimal-case",
            current_stage="act1",
            current_stage_order=10,
            character_id="player",
        ),
    )
    unlocked_results = await retriever.retrieve(
        "线索一",
        RagSessionContext(
            script_id="minimal-case",
            current_stage="act1",
            current_stage_order=10,
            character_id="player",
            unlocked_clue_ids=("clue_1",),
        ),
    )

    assert all(result.chunk.source_id != "clue_1" for result in locked_results)
    assert any(result.chunk.source_id == "clue_1" for result in unlocked_results)


async def test_retrieve_orders_allowed_candidates_by_bm25_keyword_score() -> None:
    # Given: two visible chunks with identical vector similarity but different term density.
    retriever = RagRetriever(
        StaticEmbeddingProvider(),
        InMemoryRagRepository(
            (
                _record("sparse", "凶手 背景 背景 背景 背景 背景 背景 背景"),
                _record("dense", "凶手 凶手 凶手"),
            ),
        ),
    )
    context = RagSessionContext(
        script_id="minimal-case",
        current_stage="act1",
        current_stage_order=10,
        character_id="player",
    )

    # When: retrieval combines equal vectors with keyword relevance.
    results = await retriever.retrieve("凶手", context, limit=2)

    # Then: BM25 length normalization promotes the denser candidate.
    assert results[0].chunk.source_id == "dense"
    assert results[0].keyword_score > results[1].keyword_score


async def test_in_memory_retrieval_stays_under_latency_budget() -> None:
    retriever = _rag_retriever()
    context = RagSessionContext(
        script_id="minimal-case",
        current_stage="act1",
        current_stage_order=10,
        character_id="player",
        unlocked_clue_ids=("clue_1", "clue_2", "clue_3", "clue_4"),
    )

    latencies: list[float] = []
    for _ in range(20):
        started_at = perf_counter()
        await retriever.retrieve("线索一", context)
        latencies.append(perf_counter() - started_at)
    p95_latency = sorted(latencies)[18]

    assert p95_latency < 0.2


def test_retrieval_sql_contains_hard_permission_filters() -> None:
    sql = str(build_retrieval_sql())

    assert "script_id = :script_id" in sql
    assert "metadata ->> 'stage_order'" in sql
    assert "metadata ->> 'visibility' = 'public'" in sql
    assert "metadata ->> 'character_id' = :character_id" in sql
    assert "source_type <> 'clue'" in sql
    assert "source_id = ANY(CAST(:unlocked_clue_ids AS text[]))" in sql


def _rag_retriever() -> RagRetriever:
    provider = DeterministicEmbeddingProvider()
    records = build_index_records(chunk_package(rag_package()), provider)
    return RagRetriever(provider, InMemoryRagRepository(records))


def _record(source_id: str, text_value: str) -> RagIndexRecord:
    return RagIndexRecord(
        chunk=RagChunk(
            script_id="minimal-case",
            source_type="script_context",
            source_id=source_id,
            chunk_index=0,
            text=text_value,
            metadata={"visibility": "public", "stage_order": 0},
        ),
        embedding=(1.0, 0.0),
    )


class StaticEmbeddingProvider:
    def embed_documents(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        return tuple((1.0, 0.0) for _ in texts)

    def embed_query(self, text: str) -> tuple[float, ...]:
        return (1.0, 0.0)
