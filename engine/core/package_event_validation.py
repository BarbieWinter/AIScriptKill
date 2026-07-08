from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError
from engine.core.package_validation_context import (
    SUPPORTED_EVENT_ACTIONS,
    PackageValidationContext,
    ensure_reference,
    metadata_texts,
    required_text,
)


def validate_events(
    owner: str,
    events: tuple[dict[str, JsonValue], ...] | list[dict[str, JsonValue]],
    context: PackageValidationContext,
) -> None:
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
