from __future__ import annotations

from typing import ClassVar, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

# ── JSON 与 API 基类 ──

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ApiModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="forbid")


# ── 媒体与事件通用模型 ──


class MediaTrigger(ApiModel):
    action: str = Field(description="Media action such as play_audio.")
    asset_id: str = Field(description="Media asset identifier.")


class EventTrigger(ApiModel):
    action: str = Field(description="Engine event action.")
    asset_id: str | None = Field(default=None, description="Optional asset ID.")
    text: str | None = Field(default=None, description="Optional narration text.")


class PendingMedia(ApiModel):
    id: str = Field(description="Media asset ID.")
    type: str = Field(description="Media category.")
    status: str = Field(description="Playback status.")


class DiscoveredClue(ApiModel):
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
