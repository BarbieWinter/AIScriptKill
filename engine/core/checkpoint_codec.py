from base64 import b64decode, b64encode
from dataclasses import dataclass
from typing import Any, TypeGuard

from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    PendingWrite,
)

from engine.api.schemas.common import JsonValue

ENCODING_VERSION = 1


@dataclass(frozen=True, slots=True)
class StoredCheckpoint:
    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    pending_writes: list[PendingWrite]


def encode_stored_checkpoint(
    *,
    checkpoint: Checkpoint,
    metadata: CheckpointMetadata,
    pending_writes: list[PendingWrite],
) -> dict[str, JsonValue]:
    return {
        "version": ENCODING_VERSION,
        "checkpoint": encode_typed(checkpoint),
        "metadata": encode_typed(metadata),
        "pending_writes": [encode_typed(write) for write in pending_writes],
    }


def decode_stored_checkpoint(raw: JsonValue) -> StoredCheckpoint:
    if not isinstance(raw, dict):
        raise CheckpointStorageError("state")
    checkpoint = decode_checkpoint(raw.get("checkpoint"))
    metadata = decode_metadata(raw.get("metadata"))
    pending_writes_value = raw.get("pending_writes")
    pending_writes = (
        [decode_typed_write(item) for item in pending_writes_value if isinstance(item, dict)]
        if isinstance(pending_writes_value, list)
        else []
    )
    return StoredCheckpoint(
        checkpoint=checkpoint,
        metadata=metadata,
        pending_writes=pending_writes,
    )


def encode_typed(value: Any) -> dict[str, JsonValue]:
    type_name, payload = BaseCheckpointSaver.serde.dumps_typed(value)
    return {"type": type_name, "payload": b64encode(payload).decode("ascii")}


def decode_checkpoint(raw: JsonValue | None) -> Checkpoint:
    value = decode_typed(raw)
    if is_checkpoint(value):
        return value
    raise CheckpointStorageError("checkpoint")


def decode_metadata(raw: JsonValue | None) -> CheckpointMetadata:
    value = decode_typed(raw)
    if is_checkpoint_metadata(value):
        return value
    raise CheckpointStorageError("metadata")


def decode_typed_write(raw: dict[str, JsonValue]) -> PendingWrite:
    value = decode_typed(raw)
    if is_pending_write(value):
        return value
    raise CheckpointStorageError("pending_write")


def decode_typed(raw: JsonValue | None) -> Any:
    if not isinstance(raw, dict):
        raise CheckpointStorageError("typed")
    type_name = raw.get("type")
    payload = raw.get("payload")
    if not isinstance(type_name, str) or not isinstance(payload, str):
        raise CheckpointStorageError("typed_fields")
    return BaseCheckpointSaver.serde.loads_typed((type_name, b64decode(payload)))


def is_checkpoint(value: Any) -> TypeGuard[Checkpoint]:
    return (
        isinstance(value, dict)
        and isinstance(value.get("v"), int)
        and isinstance(value.get("id"), str)
        and isinstance(value.get("ts"), str)
        and isinstance(value.get("channel_values"), dict)
        and isinstance(value.get("channel_versions"), dict)
        and isinstance(value.get("versions_seen"), dict)
        and ("updated_channels" in value)
    )


def is_checkpoint_metadata(value: Any) -> TypeGuard[CheckpointMetadata]:
    return isinstance(value, dict)


def is_pending_write(value: Any) -> TypeGuard[PendingWrite]:
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[0], str)
        and isinstance(value[1], str)
    )


@dataclass(frozen=True, slots=True)
class CheckpointStorageError(Exception):
    field: str

    def __str__(self) -> str:
        return f"invalid stored LangGraph checkpoint field: {self.field}"
