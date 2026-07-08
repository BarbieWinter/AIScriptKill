from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import ActionType, JsonValue

# ── 运行时状态快照 ──


class SessionRuntimeState(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    player_name: str = Field(default="")
    current_stage: str = Field(default="prologue")
    stage_name: str = Field(default="序章")
    available_actions: list[ActionType] = Field(
        default_factory=lambda: ["talk_to_npc", "examine_scene", "open_clue_board"],
    )
    available_characters: list[str] = Field(default_factory=list)
    unlocked_clues: list[str] = Field(default_factory=list)
    discovered_evidences: list[str] = Field(default_factory=list)
    current_scene: str = Field(default="start")
    pending_media: list[dict[str, str]] = Field(default_factory=list)
    final_submission: dict[str, str | list[str]] | None = Field(default=None)
    ending_id: str | None = Field(default=None)


class StoredSession(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    id: UUID
    script_id: str
    player_id: UUID | None
    player_character_id: str
    state: SessionRuntimeState
    status: str
    created_at: datetime
    updated_at: datetime


# ── 检查点与行动副作用 ──


@dataclass(frozen=True, slots=True)
class SessionCheckpoint:
    id: UUID
    thread_ts: str
    state: SessionRuntimeState


@dataclass(frozen=True, slots=True)
class SessionActionEffect:
    state_patch: dict[str, JsonValue]
    chat_messages: tuple["ChatMessageDraft", ...] = ()
    discoveries: tuple["DiscoveryDraft", ...] = ()


# ── 写入草稿对象 ──


@dataclass(frozen=True, slots=True)
class ChatMessageDraft:
    role: str
    text: str
    character_id: str | None = None
    emotion: str | None = None


@dataclass(frozen=True, slots=True)
class DiscoveryDraft:
    entity_type: str
    entity_id: str
    status: str = "unlocked"
