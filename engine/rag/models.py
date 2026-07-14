from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, TypeAlias

from engine.core.package_schema import JsonMapping

RagSourceType: TypeAlias = Literal[
    "character_knowledge",
    "clue",
    "script_context",
    "evidence",
]
RagVisibility: TypeAlias = Literal["public", "character_only", "dm_only"]
EmbeddingVector: TypeAlias = tuple[float, ...]


@dataclass(frozen=True, slots=True)
class RagChunk:
    script_id: str
    source_type: RagSourceType
    source_id: str
    chunk_index: int
    text: str
    metadata: JsonMapping


@dataclass(frozen=True, slots=True)
class RagIndexRecord:
    chunk: RagChunk
    embedding: EmbeddingVector


@dataclass(frozen=True, slots=True)
class RagChunkKey:
    script_id: str
    source_type: RagSourceType
    source_id: str
    chunk_index: int


@dataclass(frozen=True, slots=True)
class RagChunkFingerprint:
    key: RagChunkKey
    content_hash: str


@dataclass(frozen=True, slots=True)
class RagIndexingResult:
    indexed_records: tuple[RagIndexRecord, ...]
    unchanged_count: int
    removed_count: int


@dataclass(frozen=True, slots=True)
class RagSessionContext:
    script_id: str
    current_stage: str
    current_stage_order: int
    viewer_character_id: str
    speaker_character_id: str | None = None
    unlocked_clue_ids: tuple[str, ...] = ()
    is_dm: bool = False


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str | None
    chunk: RagChunk
    vector_score: float
    keyword_score: float
    score: float


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

    def embed_query(self, text: str) -> Sequence[float]: ...
