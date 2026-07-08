from json import dumps

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping
from engine.rag.metadata import content_hash, metadata_text
from engine.rag.models import RagChunk, RagSourceType


def source_chunks(
    source_type: RagSourceType,
    source_id: str,
    text: str,
    metadata: JsonMapping,
    max_chars: int,
) -> tuple[RagChunk, ...]:
    return tuple(
        RagChunk(
            script_id=metadata_text(metadata, "script_id"),
            source_type=source_type,
            source_id=source_id,
            chunk_index=index,
            text=chunk,
            metadata={
                **metadata,
                "source_id": source_id,
                "chunk_index": index,
                "content_hash": content_hash(chunk),
            },
        )
        for index, chunk in enumerate(semantic_slices(text, max_chars))
    )


def semantic_slices(text: str, max_chars: int) -> tuple[str, ...]:
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return ()
    if len(normalized) <= max_chars:
        return (normalized,)
    return tuple(
        normalized[index : index + max_chars] for index in range(0, len(normalized), max_chars)
    )


def stage_order(stage_orders: dict[str, int], stage_id: str) -> int:
    return stage_orders.get(stage_id, 0)


def json_summary(value: JsonValue) -> str:
    return dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
