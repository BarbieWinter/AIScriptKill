"""在 JSON 数据库边界编码并校验检查点值。"""

from base64 import b64decode, b64encode
from binascii import Error as BinasciiError
from dataclasses import dataclass
from typing import Any, Final, TypeGuard, cast

from langgraph.checkpoint.base import Checkpoint, CheckpointMetadata, PendingWrite
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from engine.api.schemas.common import JsonValue

ENCODING_VERSION = 1
MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES: Final = 16 * 1024 * 1024
MAX_CHECKPOINT_PENDING_WRITES: Final = 10_000
STRICT_CHECKPOINT_SERDE: Final = JsonPlusSerializer(
    allowed_json_modules=(),
    allowed_msgpack_modules=(),
)


@dataclass(frozen=True, slots=True)
class StoredCheckpoint:
    """封装已解码检查点、元数据和旧版内嵌写入。"""

    checkpoint: Checkpoint
    metadata: CheckpointMetadata
    pending_writes: list[PendingWrite]


def encode_stored_checkpoint(
    *,
    checkpoint: Checkpoint,
    metadata: CheckpointMetadata,
    pending_writes: list[PendingWrite],
) -> dict[str, JsonValue]:
    """为 JSON 数据库列编码带版本的检查点信封。"""

    return {
        "version": ENCODING_VERSION,
        "checkpoint": encode_typed(checkpoint),
        "metadata": encode_typed(metadata),
        "pending_writes": [encode_typed(write) for write in pending_writes],
    }


def decode_stored_checkpoint(raw: JsonValue) -> StoredCheckpoint:
    """在大小预算内校验并解码带版本的检查点信封。"""

    if not isinstance(raw, dict):
        raise CheckpointStorageError("state")
    version = raw.get("version")
    if type(version) is not int or version != ENCODING_VERSION:
        raise CheckpointStorageError("version")
    checkpoint = decode_checkpoint(raw.get("checkpoint"))
    metadata = decode_metadata(raw.get("metadata"))
    pending_writes_value = raw.get("pending_writes")
    if not isinstance(pending_writes_value, list):
        raise CheckpointStorageError("pending_writes")
    if len(pending_writes_value) > MAX_CHECKPOINT_PENDING_WRITES:
        raise CheckpointStorageError("pending_writes_limit")
    pending_writes: list[PendingWrite] = []
    for item in pending_writes_value:
        if not isinstance(item, dict):
            raise CheckpointStorageError("pending_write")
        pending_writes.append(decode_typed_write(item))
    return StoredCheckpoint(
        checkpoint=checkpoint,
        metadata=metadata,
        pending_writes=pending_writes,
    )


def encode_typed(value: Any) -> dict[str, JsonValue]:
    """在不使用对象钩子的情况下将类型化值序列化为受限 base64 JSON。"""

    type_name, payload = STRICT_CHECKPOINT_SERDE.dumps_typed(value)
    if len(payload) > MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES:
        raise CheckpointStorageError("typed_payload_limit")
    return {"type": type_name, "payload": b64encode(payload).decode("ascii")}


def decode_checkpoint(raw: JsonValue | None) -> Checkpoint:
    """解码并从结构上校验 LangGraph 检查点值。"""

    value = decode_typed(raw)
    if is_checkpoint(value):
        return value
    raise CheckpointStorageError("checkpoint")


def decode_metadata(raw: JsonValue | None) -> CheckpointMetadata:
    """将检查点元数据解码并校验为映射。"""

    value = decode_typed(raw)
    if is_checkpoint_metadata(value):
        return value
    raise CheckpointStorageError("metadata")


def decode_typed_write(raw: dict[str, JsonValue]) -> PendingWrite:
    """解码并校验一个旧版内嵌待处理写入元组。"""

    value = decode_typed(raw)
    if is_pending_write(value):
        return (value[0], value[1], value[2])
    raise CheckpointStorageError("pending_write")


def decode_typed(raw: JsonValue | None) -> Any:
    """解码一个受限类型化载荷，否则抛出 CheckpointStorageError。"""

    if not isinstance(raw, dict):
        raise CheckpointStorageError("typed")
    type_name = raw.get("type")
    payload = raw.get("payload")
    if not isinstance(type_name, str) or not isinstance(payload, str):
        raise CheckpointStorageError("typed_fields")
    maximum_base64_length = ((MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES + 2) // 3) * 4
    if len(payload) > maximum_base64_length:
        raise CheckpointStorageError("typed_payload_limit")
    try:
        decoded_payload = b64decode(payload, validate=True)
    except BinasciiError as error:
        raise CheckpointStorageError("typed_payload") from error
    try:
        if len(decoded_payload) > MAX_CHECKPOINT_TYPED_PAYLOAD_BYTES:
            raise CheckpointStorageError("typed_payload_limit")
        return STRICT_CHECKPOINT_SERDE.loads_typed((type_name, decoded_payload))
    except CheckpointStorageError:
        raise
    except Exception as error:
        raise CheckpointStorageError("typed_payload") from error


def is_checkpoint(value: object) -> TypeGuard[Checkpoint]:
    """将已解码对象收窄为必需的检查点结构。"""

    if not isinstance(value, dict):
        return False
    mapping = cast(dict[object, object], value)
    return (
        isinstance(mapping.get("v"), int)
        and isinstance(mapping.get("id"), str)
        and isinstance(mapping.get("ts"), str)
        and isinstance(mapping.get("channel_values"), dict)
        and isinstance(mapping.get("channel_versions"), dict)
        and isinstance(mapping.get("versions_seen"), dict)
        and ("updated_channels" in mapping)
    )


def is_checkpoint_metadata(value: object) -> TypeGuard[CheckpointMetadata]:
    """将已解码对象收窄为检查点元数据。"""

    return isinstance(value, dict)


def is_pending_write(value: object) -> TypeGuard[tuple[str, str, Any] | list[Any]]:
    """将已解码对象收窄为三元素待处理写入。"""

    if not isinstance(value, (tuple, list)):
        return False
    items = cast(tuple[object, ...] | list[object], value)
    return len(items) == 3 and isinstance(items[0], str) and isinstance(items[1], str)


class CheckpointStorageError(Exception):
    """标识不可信检查点边界上的无效字段。"""

    def __init__(self, field: str) -> None:
        super().__init__(field)
        self.field = field

    def __str__(self) -> str:
        return f"invalid stored LangGraph checkpoint field: {self.field}"
