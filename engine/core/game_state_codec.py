"""将持久化 JSON 值解码为严格的游戏状态模型。"""

from collections.abc import Mapping

from engine.api.schemas.common import JsonValue
from engine.core.game_state import (
    BlockedTransition,
    CardUsageRecord,
    ClueDiscovery,
    EventActionRecord,
    EvidencePresentation,
    GameEvent,
    GameState,
    Message,
    PlayerActionInput,
    PlayerActionRecord,
    RuntimeScalar,
    clone_game_state,
    create_initial_state,
)


def game_state_from_mapping(raw: Mapping[str, JsonValue]) -> GameState:
    """重建完整 GameState，同时规范化格式错误的可选字段。"""

    state = create_initial_state(
        session_id=_text(raw, "session_id"),
        script_id=_text(raw, "script_id"),
        player_id=_text(raw, "player_id"),
        player_character_id=_text(raw, "player_character_id"),
        entry_stage=_text(raw, "current_stage", "prologue"),
    )
    state["previous_stage"] = _text_or_none(raw, "previous_stage")
    state["next_stage"] = _text_or_none(raw, "next_stage")
    state["completed_stages"] = _text_list(raw.get("completed_stages"))
    state["completed_acts"] = _text_list(raw.get("completed_acts"))
    state["stage_entered_at"] = _text(raw, "stage_entered_at")
    state["current_time"] = _text(raw, "current_time")
    state["stage_history"] = _text_list(raw.get("stage_history")) or [state["current_stage"]]
    state["npc_agents"] = _runtime_dict(raw.get("npc_agents"))
    state["npc_states"] = _runtime_dict(raw.get("npc_states"))
    state["available_actions"] = _text_list(raw.get("available_actions"))
    state["available_characters"] = _text_list(raw.get("available_characters"))
    state["available_scenes"] = _text_list(raw.get("available_scenes"))
    state["unlocked_scenes"] = _text_list(raw.get("unlocked_scenes"))
    state["current_scene"] = _text(raw, "current_scene")
    state["unlocked_clues"] = _text_list(raw.get("unlocked_clues"))
    state["discovered_evidences"] = _text_list(raw.get("discovered_evidences"))
    state["viewed_evidences"] = _subset_text_list(
        raw.get("viewed_evidences"),
        state["discovered_evidences"],
    )
    state["unlocked_character_chapters"] = _text_list(raw.get("unlocked_character_chapters"))
    state["read_character_chapters"] = _subset_text_list(
        raw.get("read_character_chapters"),
        state["unlocked_character_chapters"],
    )
    state["completed_events"] = _text_list(raw.get("completed_events"))
    state["pending_media"] = _json_mapping_list(raw.get("pending_media"))
    state["pending_npc_responses"] = _json_mapping_list(raw.get("pending_npc_responses"))
    state["character_dialog_counts"] = _int_dict(raw.get("character_dialog_counts"))
    state["triggered_dialogs"] = _text_list(raw.get("triggered_dialogs"))
    state["player_utterances"] = _text_list(raw.get("player_utterances"))
    state["player_requests"] = _text_list(raw.get("player_requests"))
    state["condition_cache"] = _bool_dict(raw.get("condition_cache"))
    state["ending_triggered"] = _bool(raw, "ending_triggered")
    state["ending_id"] = _text_or_none(raw, "ending_id")
    state["final_submission"] = _json_mapping_or_none(raw.get("final_submission"))
    state["answer_key"] = _json_mapping(raw.get("answer_key"))
    state["deduction_chains_completed"] = _text_list(raw.get("deduction_chains_completed"))
    state["session_counters"] = _int_dict(raw.get("session_counters"))
    state["is_first_play"] = _bool(raw, "is_first_play", default=True)
    state["hint_count"] = _int(raw, "hint_count")
    state["discovered_clues"] = _clue_discoveries(raw.get("discovered_clues"))
    state["evidences_shown_to_npcs"] = _evidence_presentations(raw.get("evidences_shown_to_npcs"))
    state["event_log"] = _event_records(raw.get("event_log"))
    state["chat_history"] = _messages(raw.get("chat_history"))
    state["performed_actions"] = _player_action_records(raw.get("performed_actions"))
    state["used_cards"] = _card_usage_records(raw.get("used_cards"))
    state["pending_events"] = _game_events(raw.get("pending_events"))
    state["pending_action"] = _player_action_input(raw.get("pending_action"))
    state["blocked_transitions"] = _blocked_transitions(raw.get("blocked_transitions"))
    return clone_game_state(state)


def _text(raw: Mapping[str, JsonValue], key: str, default: str = "") -> str:
    value = raw.get(key)
    if isinstance(value, str):
        return value
    return default


def _text_or_none(raw: Mapping[str, JsonValue], key: str) -> str | None:
    value = raw.get(key)
    if isinstance(value, str):
        return value
    return None


def _bool(raw: Mapping[str, JsonValue], key: str, *, default: bool = False) -> bool:
    value = raw.get(key)
    if isinstance(value, bool):
        return value
    return default


def _int(raw: Mapping[str, JsonValue], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, int):
        return value
    return 0


def _text_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _subset_text_list(value: JsonValue | None, allowed: list[str]) -> list[str]:
    return [item for item in _text_list(value) if item in allowed]


def _json_mapping(value: JsonValue | None) -> dict[str, JsonValue]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _json_mapping_or_none(value: JsonValue | None) -> dict[str, JsonValue] | None:
    if isinstance(value, dict):
        return dict(value)
    return None


def _json_mapping_list(value: JsonValue | None) -> list[dict[str, JsonValue]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _runtime_dict(value: JsonValue | None) -> dict[str, dict[str, RuntimeScalar]]:
    results: dict[str, dict[str, RuntimeScalar]] = {}
    if not isinstance(value, dict):
        return results
    for key, nested in value.items():
        if isinstance(nested, dict):
            results[key] = _runtime_scalar_dict(nested)
    return results


def _runtime_scalar_dict(value: Mapping[str, JsonValue]) -> dict[str, RuntimeScalar]:
    result: dict[str, RuntimeScalar] = {}
    for key, item in value.items():
        if isinstance(item, str | int | float | bool) or item is None:
            result[key] = item
    return result


def _int_dict(value: JsonValue | None) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(item, int)}


def _bool_dict(value: JsonValue | None) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if isinstance(item, bool)}


def _clue_discoveries(value: JsonValue | None) -> list[ClueDiscovery]:
    return [
        {
            "clue_id": _text(item, "clue_id"),
            "round_id": _text(item, "round_id"),
            "scene_id": _text(item, "scene_id"),
            "is_key": _bool(item, "is_key"),
        }
        for item in _json_mapping_list(value)
    ]


def _evidence_presentations(value: JsonValue | None) -> list[EvidencePresentation]:
    return [
        {"evidence_id": _text(item, "evidence_id"), "character_id": _text(item, "character_id")}
        for item in _json_mapping_list(value)
    ]


def _event_records(value: JsonValue | None) -> list[EventActionRecord]:
    return [
        {
            "event_id": _text(item, "event_id"),
            "source": _text(item, "source"),
            "action": _text(item, "action"),
            "payload": _json_mapping(item.get("payload")),
        }
        for item in _json_mapping_list(value)
    ]


def _messages(value: JsonValue | None) -> list[Message]:
    return [
        {
            "id": _text(item, "id"),
            "role": _text(item, "role"),
            "character_id": _text_or_none(item, "character_id"),
            "text": _text(item, "text"),
            "emotion": _text_or_none(item, "emotion"),
            "timestamp": _text(item, "timestamp"),
        }
        for item in _json_mapping_list(value)
    ]


def _player_action_records(value: JsonValue | None) -> list[PlayerActionRecord]:
    return [
        {"action_id": _text(item, "action_id"), "target": _text_or_none(item, "target")}
        for item in _json_mapping_list(value)
    ]


def _card_usage_records(value: JsonValue | None) -> list[CardUsageRecord]:
    return [
        {"card_id": _text(item, "card_id"), "card_type": _text_or_none(item, "card_type")}
        for item in _json_mapping_list(value)
    ]


def _game_events(value: JsonValue | None) -> list[GameEvent]:
    return [
        {
            "event_id": _text(item, "event_id"),
            "actions": _json_mapping_list(item.get("actions")),
            "source": _text(item, "source"),
        }
        for item in _json_mapping_list(value)
    ]


def _player_action_input(value: JsonValue | None) -> PlayerActionInput | None:
    if not isinstance(value, dict):
        return None
    action_id = value.get("action_id")
    match action_id:
        case (
            "talk_to_npc"
            | "examine_scene"
            | "show_evidence"
            | "use_card"
            | "open_clue_board"
            | "request_advance"
        ):
            target = value.get("target")
            text = value.get("text")
            return PlayerActionInput(
                action_id=action_id,
                target=target if isinstance(target, str) else None,
                text=text if isinstance(text, str) else None,
            )
        case _:
            return None


def _blocked_transitions(value: JsonValue | None) -> list[BlockedTransition]:
    return [
        {
            "from_stage": _text(item, "from_stage"),
            "to_stage": _text(item, "to_stage"),
            "reason": _text(item, "reason"),
        }
        for item in _json_mapping_list(value)
    ]
