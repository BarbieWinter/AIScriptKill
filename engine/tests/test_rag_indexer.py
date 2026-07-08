from collections.abc import Sequence

from engine.rag.chunker import chunk_package
from engine.rag.embeddings import DeterministicEmbeddingProvider
from engine.rag.indexer import build_index_records, index_package
from engine.rag.models import (
    RagChunk,
    RagChunkFingerprint,
    RagChunkKey,
    RagIndexRecord,
)
from engine.tests.rag_fixtures import rag_package


def test_build_index_records_embeds_chunks_for_script_knowledge_rows() -> None:
    chunks = chunk_package(rag_package())[:4]
    provider = DeterministicEmbeddingProvider()

    records = build_index_records(chunks, provider)

    assert tuple(record.chunk for record in records) == chunks
    assert all(len(record.embedding) == 1536 for record in records)
    assert all(record.chunk.metadata["source_id"] == record.chunk.source_id for record in records)
    assert all(isinstance(record.chunk.metadata["content_hash"], str) for record in records)


async def test_index_package_skips_embedding_when_chunk_hashes_are_unchanged() -> None:
    package = rag_package()
    chunks = chunk_package(package)
    repository = RecordingRagIndexRepository(existing=_fingerprints(chunks))
    provider = RecordingEmbeddingProvider()

    result = await index_package(package, repository, provider)

    assert provider.embedded_texts == ()
    assert repository.updated_records == ()
    assert repository.removed_keys == ()
    assert result.unchanged_count == len(chunks)


async def test_index_package_only_reindexes_changed_and_removed_chunks() -> None:
    package = rag_package()
    chunks = chunk_package(package)
    obsolete_key = RagChunkKey(
        script_id=package.package.id,
        source_type="script_context",
        source_id="removed",
        chunk_index=0,
    )
    existing = (
        _changed_fingerprint(chunks[0]),
        *_fingerprints(chunks[1:]),
        RagChunkFingerprint(key=obsolete_key, content_hash="old"),
    )
    repository = RecordingRagIndexRepository(existing=existing)
    provider = RecordingEmbeddingProvider()

    result = await index_package(package, repository, provider)

    assert provider.embedded_texts == (chunks[0].text,)
    assert tuple(record.chunk for record in repository.updated_records) == (chunks[0],)
    assert repository.removed_keys == (obsolete_key,)
    assert result.unchanged_count == len(chunks) - 1
    assert result.removed_count == 1


class RecordingEmbeddingProvider:
    def __init__(self) -> None:
        self.embedded_texts: tuple[str, ...] = ()

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        self.embedded_texts = tuple(texts)
        return tuple((1.0, *([0.0] * 1535)) for _text in texts)

    def embed_query(self, text: str) -> Sequence[float]:
        return (1.0, *([0.0] * 1535))


class RecordingRagIndexRepository:
    def __init__(self, existing: Sequence[RagChunkFingerprint]) -> None:
        self._existing = tuple(existing)
        self.updated_records: tuple[RagIndexRecord, ...] = ()
        self.removed_keys: tuple[RagChunkKey, ...] = ()

    async def list_chunk_fingerprints(self, script_id: str) -> tuple[RagChunkFingerprint, ...]:
        return tuple(
            fingerprint for fingerprint in self._existing if fingerprint.key.script_id == script_id
        )

    async def apply_incremental_update(
        self,
        script_id: str,
        records: Sequence[RagIndexRecord],
        removed_keys: Sequence[RagChunkKey],
    ) -> None:
        self.updated_records = tuple(records)
        self.removed_keys = tuple(removed_keys)


def _fingerprints(chunks: Sequence[RagChunk]) -> tuple[RagChunkFingerprint, ...]:
    return tuple(_fingerprint(chunk) for chunk in chunks)


def _fingerprint(chunk: RagChunk) -> RagChunkFingerprint:
    content_hash = chunk.metadata["content_hash"]
    assert isinstance(content_hash, str)
    return RagChunkFingerprint(
        key=RagChunkKey(
            script_id=chunk.script_id,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            chunk_index=chunk.chunk_index,
        ),
        content_hash=content_hash,
    )


def _changed_fingerprint(chunk: RagChunk) -> RagChunkFingerprint:
    return RagChunkFingerprint(key=_fingerprint(chunk).key, content_hash="changed")
