"""定义 Multiplayer v1 的稳定错误码和命令错误信封。"""

from enum import StrEnum

from pydantic import Field, JsonValue

from engine.contracts.multiplayer_v1.base import ContractModel


class MultiplayerErrorCode(StrEnum):
    """跨命令和传输边界保持稳定的多人错误码。"""

    AUTH_REQUIRED = "AUTH_REQUIRED"
    NOT_ROOM_MEMBER = "NOT_ROOM_MEMBER"
    PRIVATE_CONTENT_FORBIDDEN = "PRIVATE_CONTENT_FORBIDDEN"
    REVISION_MISMATCH = "REVISION_MISMATCH"
    COMMAND_ID_REUSED = "COMMAND_ID_REUSED"
    PHASE_MISMATCH = "PHASE_MISMATCH"
    SETTLEMENT_ALREADY_SUBMITTED = "SETTLEMENT_ALREADY_SUBMITTED"
    INVALID_COMMAND = "INVALID_COMMAND"
    UNSUPPORTED_PROTOCOL_VERSION = "UNSUPPORTED_PROTOCOL_VERSION"
    FEATURE_DISABLED = "FEATURE_DISABLED"


class CommandError(ContractModel):
    """描述被拒绝命令的机器码和安全公开信息。"""

    code: MultiplayerErrorCode
    message: str = Field(min_length=1)
    details: dict[str, JsonValue] = Field(default_factory=dict)
