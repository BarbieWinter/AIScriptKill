"""持久多人命令及 HTTP replay 的严格 wire models。"""

from typing import Literal
from uuid import UUID

from pydantic import Field

from engine.api.schemas.actions import ActionResponse
from engine.api.schemas.common import ApiModel


class CommandActionResponse(ApiModel):
    """返回一次已持久化命令的权威结果。"""

    command_id: UUID
    status: Literal["succeeded", "rejected", "failed"]
    revision: int = Field(ge=0)
    event_sequence_from: int | None = Field(default=None, ge=1)
    event_sequence_to: int | None = Field(default=None, ge=1)
    result: ActionResponse | None = None
    error_code: str | None = None
    error_details: dict[str, object] = Field(default_factory=dict)


class CommandReceiptResponse(ApiModel):
    """返回命令 receipt 的可重放状态。"""

    command_id: UUID
    status: Literal["processing", "succeeded", "rejected", "failed"]
    revision: int = Field(ge=0)
    event_sequence_from: int | None = Field(default=None, ge=1)
    event_sequence_to: int | None = Field(default=None, ge=1)
    result: ActionResponse | dict[str, object] | None = None
    error_code: str | None = None
    error_details: dict[str, object] = Field(default_factory=dict)


class SessionEvent(ApiModel):
    """participant-safe 的公开事件；不得包含完整 GameState。"""

    sequence: int = Field(ge=1)
    revision: int = Field(ge=0)
    command_id: UUID
    event_type: str = Field(min_length=1)
    event_version: int = Field(default=1, ge=1)
    payload: dict[str, object]
    state_sha256: str | None = None


class SessionEventPage(ApiModel):
    """从游标读取的有序事件页及权威状态摘要。"""

    revision: int = Field(ge=0)
    event_head_sequence: int = Field(ge=0)
    snapshot: object
    events: list[SessionEvent]
    next_after_sequence: int = Field(ge=0)
    has_more: bool
    reset_required: bool = False
