from dataclasses import dataclass

from engine.core.condition_leaf_helpers import (
    clues_label,
    compare_state_value,
    count_matches,
    matching_clues,
    optional_label,
    parse_time,
    submitted_key_evidence_ids,
)
from engine.core.condition_models import ConditionNode
from engine.core.condition_trace import ConditionTraceNode
from engine.core.game_state import GameState


@dataclass(frozen=True, slots=True)
class LeafEvaluation:
    value: bool
    label: str
    detail: str | None = None

    def to_trace(self) -> ConditionTraceNode:
        return ConditionTraceNode(label=self.label, value=self.value, detail=self.detail)


def stage_completed(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.1 游戏进度条件。
    stage_id = condition.required_text("stage_id")
    return LeafEvaluation(stage_id in state["completed_stages"], f"stage_completed({stage_id})")


def stage_reached(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.1 游戏进度条件。
    stage_id = condition.required_text("stage_id")
    reached = stage_id == state["current_stage"] or stage_id in state["completed_stages"]
    return LeafEvaluation(reached, f"stage_reached({stage_id})")


def act_completed(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.1 游戏进度条件。
    act_id = condition.required_text("act_id")
    return LeafEvaluation(act_id in state["completed_acts"], f"act_completed({act_id})")


def clues_discovered(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.2 线索和证物条件。
    clues = matching_clues(condition, state)
    count = len(clues)
    value = count_matches(
        count,
        condition.integer("min_count", 0),
        condition.integer("max_count", count),
        condition.integer("exact_count", -1),
    )
    return LeafEvaluation(value, clues_label(condition), f"{count} found")


def clue_discovered(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.2 线索和证物条件。
    clue_id = condition.required_text("clue_id")
    return LeafEvaluation(clue_id in state["unlocked_clues"], f"clue_discovered({clue_id})")


def evidence_found(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.2 线索和证物条件。
    evidence_id = condition.required_text("evidence_id")
    return LeafEvaluation(
        evidence_id in state["discovered_evidences"],
        f"evidence_found({evidence_id})",
    )


def evidence_shown_to_npc(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.2 线索和证物条件。
    evidence_id = condition.required_text("evidence_id")
    character_id = condition.required_text("character_id")
    shown = any(
        item["evidence_id"] == evidence_id and item["character_id"] == character_id
        for item in state["evidences_shown_to_npcs"]
    )
    return LeafEvaluation(shown, f"evidence_shown_to_npc({evidence_id}, {character_id})")


def character_talked_to(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.3 对话交互条件。
    character_id = condition.required_text("character_id")
    count = state["character_dialog_counts"].get(character_id, 0)
    minimum = condition.integer("min_count", 1)
    return LeafEvaluation(
        count >= minimum,
        f"character_talked_to({character_id})",
        f"{count} talks",
    )


def dialog_triggered(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.3 对话交互条件。
    dialog_id = condition.required_text("dialog_id")
    return LeafEvaluation(dialog_id in state["triggered_dialogs"], f"dialog_triggered({dialog_id})")


def player_said_keyword(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.3 对话交互条件。
    keyword = condition.required_text("keyword")
    case_sensitive = condition.boolean("case_sensitive")
    utterances = state["player_utterances"]
    if case_sensitive:
        matched = any(keyword in utterance for utterance in utterances)
    else:
        matched = any(keyword.lower() in utterance.lower() for utterance in utterances)
    return LeafEvaluation(matched, f"player_said_keyword({keyword})")


def npc_state_reached(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.3 对话交互条件。
    character_id = condition.required_text("character_id")
    state_name = condition.required_text("state")
    value = state["npc_states"].get(character_id, {}).get(state_name)
    threshold = condition.integer("threshold", 0)
    matched = compare_state_value(value, threshold, condition.text("comparison") or "gte")
    return LeafEvaluation(matched, f"npc_state_reached({character_id}, {state_name})")


def player_action_performed(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.4 玩家行为条件。
    action_id = condition.required_text("action_id")
    target = condition.text("target")
    matched = any(
        action["action_id"] == action_id and (target is None or action["target"] == target)
        for action in state["performed_actions"]
    )
    return LeafEvaluation(matched, f"player_action_performed({action_id})")


def player_requested(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.4 玩家行为条件。
    dialog_id = condition.text("dialog_id")
    if dialog_id is None:
        matched = len(state["player_requests"]) > 0
    else:
        matched = dialog_id in state["player_requests"]
    return LeafEvaluation(matched, optional_label("player_requested", dialog_id))


def player_used_card(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.4 玩家行为条件。
    card_id = condition.text("card_id")
    card_type = condition.text("card_type")
    matched = any(
        (card_id is None or card["card_id"] == card_id)
        and (card_type is None or card["card_type"] == card_type)
        for card in state["used_cards"]
    )
    return LeafEvaluation(matched, optional_label("player_used_card", card_id or card_type))


def time_elapsed(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.5 时间条件。
    minutes = condition.integer("minutes")
    elapsed = int(
        (parse_time(state["current_time"]) - parse_time(state["stage_entered_at"])).total_seconds()
        // 60,
    )
    return LeafEvaluation(
        elapsed >= minutes,
        f"time_elapsed(min={minutes})",
        f"elapsed {elapsed}min",
    )


def real_time_reached(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.5 时间条件。
    target_time = condition.required_text("time")
    reached = parse_time(state["current_time"]) >= parse_time(target_time)
    return LeafEvaluation(reached, f"real_time_reached({target_time})")


def submission_correct(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.6 提交答案条件。
    field = condition.required_text("field")
    expected = condition.parameters.get("value", state["answer_key"].get(field))
    submission = state["final_submission"] or {}
    return LeafEvaluation(submission.get(field) == expected, f"submission_correct({field})")


def submission_incorrect(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.6 提交答案条件。
    field = condition.required_text("field")
    expected = condition.parameters.get("value", state["answer_key"].get(field))
    submission = state["final_submission"] or {}
    return LeafEvaluation(submission.get(field) != expected, f"submission_incorrect({field})")


def key_evidence_used(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.6 提交答案条件。
    submission = state["final_submission"] or {}
    submitted_ids = submitted_key_evidence_ids(submission.get("key_evidences"))
    required_ids = condition.text_tuple("evidence_ids")
    minimum = condition.integer("min_count", 1)
    matched = all(evidence_id in submitted_ids for evidence_id in required_ids)
    return LeafEvaluation(matched and len(submitted_ids) >= minimum, "key_evidence_used")


def deduction_chain_complete(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.6 提交答案条件。
    chain_id = condition.required_text("chain_id")
    return LeafEvaluation(
        chain_id in state["deduction_chains_completed"],
        f"deduction_chain_complete({chain_id})",
    )


def event_triggered(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.7 事件触发条件。
    event_id = condition.required_text("event_id")
    return LeafEvaluation(event_id in state["completed_events"], f"event_triggered({event_id})")


def event_not_triggered(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.7 事件触发条件。
    event_id = condition.required_text("event_id")
    return LeafEvaluation(
        event_id not in state["completed_events"],
        f"event_not_triggered({event_id})",
    )


def session_count(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.8 全局状态条件。
    counter = condition.required_text("counter")
    count = state["session_counters"].get(counter, 0)
    return LeafEvaluation(
        count_matches(count, condition.integer("min", 0), condition.integer("max", count), -1),
        f"session_count({counter})",
    )


def hint_count_used(condition: ConditionNode, state: GameState) -> LeafEvaluation:
    # DSL §2.8 全局状态条件。
    count = state["hint_count"]
    return LeafEvaluation(
        count_matches(count, condition.integer("min", 0), condition.integer("max", count), -1),
        "hint_count_used",
    )
