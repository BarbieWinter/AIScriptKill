"""定义共享的不可变 API 模型、JSON 值和动作字面量。"""

from __future__ import annotations

from typing import ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

# ── JSON 与 API 基类 ──

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ApiModel(BaseModel):
    """禁止未知 API 字段，并使已接受的载荷不可变。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


# ── 媒体与事件通用模型 ──


class MediaTrigger(ApiModel):
    """请求客户端对已声明资源执行一次媒体动作。"""

    action: str = Field(description="Media action such as play_audio.")
    asset_id: str = Field(description="Media asset identifier.")


class EventTrigger(ApiModel):
    """描述客户端可见的引擎事件动作及可选载荷。"""

    action: str = Field(description="Engine event action.")
    asset_id: str | None = Field(default=None, description="Optional asset ID.")
    text: str | None = Field(default=None, description="Optional narration text.")


class PendingMedia(ApiModel):
    """公开一个已入队媒体资源的当前播放状态。"""

    id: str = Field(description="Media asset ID.")
    type: str = Field(description="Media category.")
    status: str = Field(description="Playback status.")


class DiscoveredClue(ApiModel):
    """标识动作响应中新揭示的线索。"""

    clue_id: str = Field(description="Unlocked clue ID.")
    name: str = Field(description="Display name.")


# ── 动作与状态通用类型 ──

StateChanges: TypeAlias = dict[str, int | float | str | bool]
ActionType: TypeAlias = Literal[
    "talk_to_npc",
    "examine_scene",
    "show_evidence",
    "use_card",
    "open_clue_board",
    "request_advance",
]
