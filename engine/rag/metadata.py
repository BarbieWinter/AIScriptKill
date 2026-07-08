from hashlib import sha256

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping
from engine.rag.models import RagSourceType, RagVisibility


def chunk_metadata(
    *,
    script_id: str,
    source_type: RagSourceType,
    visibility: RagVisibility,
    stage_visible: str,
    stage_order: int,
    character_id: str | None = None,
    importance: int = 0,
    extra: JsonMapping | None = None,
) -> JsonMapping:
    """Build the security metadata stored beside every vector chunk.

    The retriever's SQL WHERE clause reads these fields directly. Keep them
    primitive and explicit so player-side retrieval never needs to ask an LLM
    whether content is safe to reveal.
    """
    metadata: JsonMapping = {
        "script_id": script_id,
        "type": source_type,
        "source_type": source_type,
        "visibility": visibility,
        "stage_visible": stage_visible,
        "stage_order": stage_order,
        "importance": importance,
    }
    if character_id is not None:
        metadata["character_id"] = character_id
    if extra is not None:
        metadata.update(extra)
    return metadata


def metadata_text(metadata: JsonMapping, key: str, default: str = "") -> str:
    value = metadata.get(key)
    if isinstance(value, str):
        return value
    return default


def metadata_int(metadata: JsonMapping, key: str, default: int = 0) -> int:
    value = metadata.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdecimal():
        return int(value)
    return default


def json_mapping(value: JsonValue | None) -> JsonMapping:
    if isinstance(value, dict):
        return value
    return {}


def json_mapping_list(value: JsonValue | None) -> tuple[JsonMapping, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, dict))


def json_string_list(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item.strip())


def content_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()
