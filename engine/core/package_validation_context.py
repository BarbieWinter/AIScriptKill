from dataclasses import dataclass
from typing import Final

from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError

SUPPORTED_CONDITION_TYPES: Final[frozenset[str]] = frozenset(
    (
        "all",
        "any",
        "not",
        "stage_completed",
        "stage_reached",
        "act_completed",
        "clues_discovered",
        "clue_discovered",
        "evidence_found",
        "evidence_shown_to_npc",
        "character_talked_to",
        "dialog_triggered",
        "player_said_keyword",
        "npc_state_reached",
        "player_action_performed",
        "player_requested",
        "player_used_card",
        "time_elapsed",
        "real_time_reached",
        "submission_correct",
        "submission_incorrect",
        "key_evidence_used",
        "deduction_chain_complete",
        "event_triggered",
        "event_not_triggered",
        "session_count",
        "is_first_play",
        "hint_count_used",
    ),
)
SUPPORTED_EVENT_ACTIONS: Final[frozenset[str]] = frozenset(
    (
        "clue_discover",
        "dm_narrate",
        "npc_emotion",
        "npc_enter_scene",
        "play_audio",
        "save_checkpoint",
        "show_truth_summary",
        "transition_to",
        "unlock_clue_round",
        "unlock_scenes",
    ),
)
ACTION_TYPES: Final[frozenset[str]] = frozenset(
    (
        "talk_to_npc",
        "examine_scene",
        "show_evidence",
        "use_card",
        "open_clue_board",
        "request_advance",
    ),
)


@dataclass(frozen=True, slots=True)
class PackageValidationContext:
    stage_ids: frozenset[str]
    character_ids: frozenset[str]
    clue_ids: frozenset[str]
    evidence_ids: frozenset[str]
    scene_ids: frozenset[str]
    media_ids: frozenset[str]
    clue_round_ids: frozenset[str]
    ending_ids: frozenset[str]
    available_files: frozenset[str]


def ensure_reference(owner: str, reference: str, known_ids: frozenset[str]) -> None:
    if reference in known_ids:
        return
    raise PackageArchiveError(
        "PACKAGE_REFERENCE_INVALID",
        f"{owner} 指向不存在的对象: {reference}",
    )


def metadata_text(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value != "":
        return value
    return None


def metadata_texts(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item != "")


def json_mapping_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def required_mapping(
    owner: str,
    mapping: dict[str, JsonValue],
    field: str,
) -> dict[str, JsonValue]:
    value = mapping.get(field)
    if isinstance(value, dict):
        return value
    raise PackageArchiveError("PACKAGE_REFERENCE_INVALID", f"{owner} 缺少对象字段: {field}")


def required_text(owner: str, mapping: dict[str, JsonValue], field: str) -> str:
    value = metadata_text(mapping.get(field))
    if value is not None:
        return value
    raise PackageArchiveError("PACKAGE_REFERENCE_INVALID", f"{owner} 缺少文本字段: {field}")
