"""校验请求动作并记录其确定性状态效果。"""

from engine.core.game_state import GameState, PlayerActionInput
from engine.core.script_engine_errors import ScriptEngineActionError
from engine.core.script_runtime import record_dialog, record_evidence_presentation


def validate_player_action(state: GameState, action: PlayerActionInput) -> str | None:
    """校验动作可用性和目标，并返回规范化目标。"""

    return _validated_target(state, action)


def apply_player_action(state: GameState, action: PlayerActionInput) -> None:
    """记录已校验动作并更新条件可见状态字段。"""

    target = validate_player_action(state, action)
    state["performed_actions"].append(
        {"action_id": action["action_id"], "target": target},
    )
    match action["action_id"]:
        case "request_advance":
            state["player_requests"].append(target or "request_advance")
        case "talk_to_npc":
            record_dialog(state, target, action["text"])
        case "examine_scene":
            state["current_scene"] = _required_target(target, "scene")
        case "show_evidence":
            record_evidence_presentation(state, target)
        case "use_card":
            state["used_cards"].append(
                {"card_id": _required_target(target, "card"), "card_type": None},
            )
        case "open_clue_board":
            return


def _validated_target(state: GameState, action: PlayerActionInput) -> str | None:
    action_id = action["action_id"]
    if action_id not in state["available_actions"]:
        raise ScriptEngineActionError(
            "ACTION_NOT_AVAILABLE",
            f"当前阶段未启用动作: {action_id}",
        )
    target = action["target"]
    match action_id:
        case "talk_to_npc":
            return _available_target(target, state["available_characters"], "character")
        case "examine_scene":
            return _available_target(target, state["available_scenes"], "scene")
        case "show_evidence":
            # T-2.6 映射器会在进入核心图之前，
            # 将证物和角色字段编码为 evidence_id:character_id。
            evidence_id, character_id = _evidence_target(target)
            if evidence_id not in state["discovered_evidences"]:
                raise ScriptEngineActionError(
                    "EVIDENCE_NOT_DISCOVERED",
                    f"证物尚未发现: {evidence_id}",
                )
            if character_id not in state["available_characters"]:
                raise ScriptEngineActionError(
                    "ACTION_TARGET_UNAVAILABLE",
                    f"当前阶段角色不可用: {character_id}",
                )
            return f"{evidence_id}:{character_id}"
        case "use_card":
            return _required_target(target, "card")
        case "open_clue_board":
            if target not in (None, ""):
                raise ScriptEngineActionError(
                    "ACTION_TARGET_INVALID",
                    "open_clue_board 不接受 target",
                )
            return None
        case "request_advance":
            return target


def _required_target(target: str | None, target_kind: str) -> str:
    if target is None or target.strip() == "":
        raise ScriptEngineActionError(
            "ACTION_TARGET_REQUIRED",
            f"{target_kind} target 不能为空",
        )
    return target


def _available_target(target: str | None, available: list[str], target_kind: str) -> str:
    value = _required_target(target, target_kind)
    if value not in available:
        raise ScriptEngineActionError(
            "ACTION_TARGET_UNAVAILABLE",
            f"当前阶段 {target_kind} target 不可用: {value}",
        )
    return value


def _evidence_target(target: str | None) -> tuple[str, str]:
    value = _required_target(target, "evidence")
    evidence_id, separator, character_id = value.partition(":")
    if separator == "" or evidence_id == "" or character_id == "" or ":" in character_id:
        raise ScriptEngineActionError(
            "ACTION_TARGET_INVALID",
            "show_evidence target 必须为 evidence_id:character_id",
        )
    return evidence_id, character_id
