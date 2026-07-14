"""将游戏状态适配为只读条件求值上下文。"""

from engine.api.schemas.common import JsonValue
from engine.core import condition_leaf_evaluators as leaves
from engine.core.condition_leaf_evaluators import LeafEvaluation
from engine.core.condition_models import ConditionDslError, ConditionNode, ConditionType
from engine.core.game_state import GameState, RuntimeScalar
from engine.core.package_schema import JsonMapping


def evaluate_leaf(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    """将一个非复合 DSL 节点分派到第 2 节对应的求值器。"""

    # DSL §2-§3 叶子调度：常量条件在这里处理，具体 §2.x 条件交给 leaf evaluator。
    match condition.type:
        case ConditionType.ALWAYS:
            # DSL §3 always：恒真叶子条件。
            return LeafEvaluation(True, "always")
        case ConditionType.NEVER:
            # DSL §3 never：恒假叶子条件。
            return LeafEvaluation(False, "never")
        case ConditionType.STAGE_COMPLETED:
            return leaves.stage_completed(condition, state)
        case ConditionType.STAGE_REACHED:
            return leaves.stage_reached(condition, state)
        case ConditionType.ACT_COMPLETED:
            return leaves.act_completed(condition, state)
        case ConditionType.CLUES_DISCOVERED:
            return leaves.clues_discovered(condition, state)
        case ConditionType.CLUE_DISCOVERED:
            return leaves.clue_discovered(condition, state)
        case ConditionType.EVIDENCE_FOUND:
            return leaves.evidence_found(condition, state)
        case ConditionType.EVIDENCE_VIEWED:
            return leaves.evidence_viewed(condition, state)
        case ConditionType.CHARACTER_CHAPTER_READ:
            return leaves.character_chapter_read(condition, state)
        case ConditionType.EVIDENCE_SHOWN_TO_NPC:
            return leaves.evidence_shown_to_npc(condition, state)
        case ConditionType.CHARACTER_TALKED_TO:
            return leaves.character_talked_to(condition, state)
        case ConditionType.DIALOG_TRIGGERED:
            return leaves.dialog_triggered(condition, state)
        case ConditionType.PLAYER_SAID_KEYWORD:
            return leaves.player_said_keyword(condition, state)
        case ConditionType.NPC_STATE_REACHED:
            return leaves.npc_state_reached(condition, state)
        case ConditionType.PLAYER_ACTION_PERFORMED:
            return leaves.player_action_performed(condition, state)
        case ConditionType.PLAYER_REQUESTED:
            return leaves.player_requested(condition, state)
        case ConditionType.PLAYER_USED_CARD:
            return leaves.player_used_card(condition, state)
        case ConditionType.TIME_ELAPSED:
            return leaves.time_elapsed(condition, state)
        case ConditionType.REAL_TIME_REACHED:
            return leaves.real_time_reached(condition, state)
        case ConditionType.SUBMISSION_CORRECT:
            return leaves.submission_correct(condition, state)
        case ConditionType.SUBMISSION_INCORRECT:
            return leaves.submission_incorrect(condition, state)
        case ConditionType.KEY_EVIDENCE_USED:
            return leaves.key_evidence_used(condition, state)
        case ConditionType.DEDUCTION_CHAIN_COMPLETE:
            return leaves.deduction_chain_complete(condition, state)
        case ConditionType.EVENT_TRIGGERED:
            return leaves.event_triggered(condition, state)
        case ConditionType.EVENT_NOT_TRIGGERED:
            return leaves.event_not_triggered(condition, state)
        case ConditionType.SESSION_COUNT:
            return leaves.session_count(condition, state)
        case ConditionType.IS_FIRST_PLAY:
            return LeafEvaluation(state["is_first_play"], "is_first_play")
        case ConditionType.HINT_COUNT_USED:
            return leaves.hint_count_used(condition, state)
        case ConditionType.ALL | ConditionType.ANY | ConditionType.NOT | ConditionType.COUNT:
            raise ConditionDslError(
                "CONDITION_NODE_NOT_LEAF",
                f"{condition.type.value} 是组合条件，不是叶子条件",
            )


def state_cache_snapshot(state: GameState) -> JsonMapping:
    """仅返回可能影响条件求值的状态字段。"""

    # DSL §5 缓存输入：只纳入 evaluator 会读取的状态片段，不把 condition_cache 自身入键。
    discovered_clues: list[JsonValue] = [
        {
            "clue_id": clue["clue_id"],
            "round_id": clue["round_id"],
            "scene_id": clue["scene_id"],
            "is_key": clue["is_key"],
        }
        for clue in state["discovered_clues"]
    ]
    evidence_presentations: list[JsonValue] = [
        {
            "evidence_id": item["evidence_id"],
            "character_id": item["character_id"],
        }
        for item in state["evidences_shown_to_npcs"]
    ]
    performed_actions: list[JsonValue] = [
        {"action_id": action["action_id"], "target": action["target"]}
        for action in state["performed_actions"]
    ]
    used_cards: list[JsonValue] = [
        {"card_id": card["card_id"], "card_type": card["card_type"]} for card in state["used_cards"]
    ]
    return {
        "current_stage": state["current_stage"],
        "completed_stages": list(state["completed_stages"]),
        "completed_acts": list(state["completed_acts"]),
        "stage_entered_at": state["stage_entered_at"],
        "current_time": state["current_time"],
        "npc_states": _scalar_mapping(state["npc_states"]),
        "unlocked_clues": list(state["unlocked_clues"]),
        "discovered_clues": discovered_clues,
        "discovered_evidences": list(state["discovered_evidences"]),
        "viewed_evidences": list(state["viewed_evidences"]),
        "unlocked_character_chapters": list(state["unlocked_character_chapters"]),
        "read_character_chapters": list(state["read_character_chapters"]),
        "evidences_shown_to_npcs": evidence_presentations,
        "completed_events": list(state["completed_events"]),
        "character_dialog_counts": dict(state["character_dialog_counts"]),
        "triggered_dialogs": list(state["triggered_dialogs"]),
        "player_utterances": list(state["player_utterances"]),
        "performed_actions": performed_actions,
        "player_requests": list(state["player_requests"]),
        "used_cards": used_cards,
        "final_submission": state["final_submission"] or {},
        "answer_key": dict(state["answer_key"]),
        "deduction_chains_completed": list(state["deduction_chains_completed"]),
        "session_counters": dict(state["session_counters"]),
        "is_first_play": state["is_first_play"],
        "hint_count": state["hint_count"],
    }


def _scalar_mapping(value: dict[str, dict[str, RuntimeScalar]]) -> JsonMapping:
    return {character_id: dict(states) for character_id, states in value.items()}
