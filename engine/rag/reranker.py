from engine.rag.metadata import metadata_int
from engine.rag.models import RetrievedChunk


def rerank(chunks: tuple[RetrievedChunk, ...]) -> tuple[RetrievedChunk, ...]:
    return tuple(sorted(chunks, key=_rerank_key, reverse=True))


def _rerank_key(chunk: RetrievedChunk) -> tuple[float, int]:
    importance = metadata_int(chunk.chunk.metadata, "importance", 0)
    return (chunk.score + min(importance, 100) / 1000, importance)
