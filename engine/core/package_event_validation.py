"""根据事件专用模型校验事件载荷。"""

from typing import Annotated, Final, Literal, Self, TypeAlias

from pydantic import Field, TypeAdapter, ValidationError, model_validator

from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError
from engine.core.package_validation_context import (
    SUPPORTED_EVENT_ACTIONS,
    PackageValidationContext,
    ensure_reference,
    metadata_texts,
    required_text,
)
from engine.core.package_yaml_base import PackageYamlModel, YamlMapping


class _EventPayload(PackageYamlModel):
    event_id: str | None = Field(default=None, description="Optional stable event identifier.")


class _DmNarrateEvent(_EventPayload):
    action: Literal["dm_narrate"] = Field(description="Event action discriminator.")
    text: str = Field(description="DM narration text to append.")


class _PlayAudioEvent(_EventPayload):
    action: Literal["play_audio"] = Field(description="Event action discriminator.")
    asset_id: str = Field(description="Declared media asset ID to play.")
    type: str | None = Field(default=None, description="Optional client media type override.")
    options: YamlMapping = Field(
        default_factory=dict,
        description="Optional client playback settings.",
    )


class _UnlockScenesEvent(_EventPayload):
    action: Literal["unlock_scenes"] = Field(description="Event action discriminator.")
    scene_ids: list[str] = Field(min_length=1, description="Scene IDs to unlock.")


class _UnlockClueRoundEvent(_EventPayload):
    action: Literal["unlock_clue_round"] = Field(description="Event action discriminator.")
    round_id: str = Field(description="Clue-round ID to unlock.")


class _NpcEnterSceneEvent(_EventPayload):
    action: Literal["npc_enter_scene"] = Field(description="Event action discriminator.")
    character_id: str = Field(description="Character ID entering the scene.")
    scene_id: str = Field(description="Destination scene ID.")
    dialogue: str | None = Field(default=None, description="Optional entrance dialogue.")


class _NpcEmotionEvent(_EventPayload):
    action: Literal["npc_emotion"] = Field(description="Event action discriminator.")
    character_id: str = Field(description="Character ID receiving the mood update.")
    state: str | None = Field(default=None, description="Optional NPC state label.")
    emotion: str | None = Field(default=None, description="Optional NPC emotion label.")

    @model_validator(mode="after")
    def require_emotion_value(self) -> Self:
        if self.state is None and self.emotion is None:
            raise ValueError("npc_emotion requires state or emotion")
        return self


class _ClueDiscoverEvent(_EventPayload):
    action: Literal["clue_discover"] = Field(description="Event action discriminator.")
    clue_id: str = Field(description="Clue ID to discover.")


class _TransitionEvent(_EventPayload):
    action: Literal["transition_to"] = Field(description="Event action discriminator.")
    stage_id: str = Field(description="Requested target stage ID.")


class _NoPayloadEvent(_EventPayload):
    action: Literal["save_checkpoint", "show_truth_summary"] = Field(
        description="Payload-free event action discriminator.",
    )


_TypedEventPayload: TypeAlias = Annotated[
    _DmNarrateEvent
    | _PlayAudioEvent
    | _UnlockScenesEvent
    | _UnlockClueRoundEvent
    | _NpcEnterSceneEvent
    | _NpcEmotionEvent
    | _ClueDiscoverEvent
    | _TransitionEvent
    | _NoPayloadEvent,
    Field(discriminator="action"),
]
_EVENT_PAYLOAD_ADAPTER: Final[TypeAdapter[_TypedEventPayload]] = TypeAdapter(_TypedEventPayload)


def validate_events(
    owner: str,
    events: tuple[dict[str, JsonValue], ...] | list[dict[str, JsonValue]],
    context: PackageValidationContext,
) -> None:
    """校验每个事件载荷及其引用的全部剧本包实体。"""

    for event in events:
        _validate_event(owner, event, context)


def _validate_event(
    owner: str,
    event: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    action = required_text(owner, event, "action")
    if action not in SUPPORTED_EVENT_ACTIONS:
        raise PackageArchiveError(
            "PACKAGE_EVENT_ACTION_INVALID",
            f"{owner} 使用了不支持的事件动作: {action}",
        )
    try:
        _EVENT_PAYLOAD_ADAPTER.validate_python(event)
    except ValidationError as exc:
        raise PackageArchiveError(
            "PACKAGE_EVENT_PAYLOAD_INVALID",
            f"{owner} 的 {action} 事件载荷不合法: {exc}",
        ) from exc
    _validate_event_references(owner, action, event, context)


def _validate_event_references(
    owner: str,
    action: str,
    event: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    match action:
        case "play_audio":
            ensure_reference(owner, required_text(owner, event, "asset_id"), context.media_ids)
        case "unlock_scenes":
            for scene_id in metadata_texts(event.get("scene_ids")):
                ensure_reference(owner, scene_id, context.scene_ids)
        case "unlock_clue_round":
            ensure_reference(owner, required_text(owner, event, "round_id"), context.clue_round_ids)
        case "npc_enter_scene":
            ensure_reference(
                owner,
                required_text(owner, event, "character_id"),
                context.character_ids,
            )
            ensure_reference(owner, required_text(owner, event, "scene_id"), context.scene_ids)
        case "npc_emotion":
            ensure_reference(
                owner,
                required_text(owner, event, "character_id"),
                context.character_ids,
            )
        case "clue_discover":
            ensure_reference(owner, required_text(owner, event, "clue_id"), context.clue_ids)
        case "transition_to":
            ensure_reference(owner, required_text(owner, event, "stage_id"), context.stage_ids)
        case "dm_narrate" | "save_checkpoint" | "show_truth_summary":
            return
        case _:
            return
