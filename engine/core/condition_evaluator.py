import hashlib
import json
from dataclasses import dataclass, field
from typing import assert_never

from engine.core import condition_trace
from engine.core.condition_models import (
    ConditionNode,
    ConditionType,
    ForceConditionResult,
    parse_condition,
)
from engine.core.condition_state import evaluate_leaf, state_cache_snapshot
from engine.core.condition_trace import ConditionEvaluation, ConditionTraceNode
from engine.core.game_state import GameState
from engine.core.package_schema import JsonMapping


@dataclass(frozen=True, slots=True)
class ConditionEvaluationOptions:
    force_conditions: dict[str, ForceConditionResult] = field(default_factory=dict)


def evaluate_condition(
    raw_condition: JsonMapping,
    state: GameState,
    options: ConditionEvaluationOptions | None = None,
) -> bool:
    # DSL §5 运行入口：用当前 GameState 评估原始条件树，并缓存 boolean 结果。
    evaluation_options = options or ConditionEvaluationOptions()
    cache_key = _condition_cache_key(raw_condition, state, evaluation_options)
    cached_result = state["condition_cache"].get(cache_key)
    if cached_result is not None:
        return cached_result
    condition = parse_condition(raw_condition)
    result = _evaluate(condition, state, evaluation_options).value
    state["condition_cache"][cache_key] = result
    return result


def evaluate_condition_with_trace(
    raw_condition: JsonMapping,
    state: GameState,
    options: ConditionEvaluationOptions | None = None,
) -> ConditionEvaluation:
    # DSL §7 调试入口：绕过 boolean 缓存，返回本次遍历生成的完整 trace 树。
    return _evaluate(parse_condition(raw_condition), state, options or ConditionEvaluationOptions())


def format_condition_trace(label: str, evaluation: ConditionEvaluation) -> str:
    return condition_trace.format_condition_trace(label, evaluation)


def _evaluate(
    condition: ConditionNode,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> ConditionEvaluation:
    # DSL §5 遍历调度：组合节点递归评估，叶子节点交给对应 §2.x evaluator。
    forced = _forced_result(condition, options)
    if forced is not None:
        return ConditionEvaluation(
            value=forced,
            trace=ConditionTraceNode(label=condition.type.value, value=forced, detail="forced"),
        )
    match condition.type:
        case ConditionType.ALL:
            return _evaluate_all(condition, state, options)
        case ConditionType.ANY:
            return _evaluate_any(condition, state, options)
        case ConditionType.NOT:
            return _evaluate_not(condition, state, options)
        case ConditionType.COUNT:
            return _evaluate_count(condition, state, options)
        case (
            ConditionType.ALWAYS
            | ConditionType.NEVER
            | ConditionType.STAGE_COMPLETED
            | ConditionType.STAGE_REACHED
            | ConditionType.ACT_COMPLETED
            | ConditionType.CLUES_DISCOVERED
            | ConditionType.CLUE_DISCOVERED
            | ConditionType.EVIDENCE_FOUND
            | ConditionType.EVIDENCE_SHOWN_TO_NPC
            | ConditionType.CHARACTER_TALKED_TO
            | ConditionType.DIALOG_TRIGGERED
            | ConditionType.PLAYER_SAID_KEYWORD
            | ConditionType.NPC_STATE_REACHED
            | ConditionType.PLAYER_ACTION_PERFORMED
            | ConditionType.PLAYER_REQUESTED
            | ConditionType.PLAYER_USED_CARD
            | ConditionType.TIME_ELAPSED
            | ConditionType.REAL_TIME_REACHED
            | ConditionType.SUBMISSION_CORRECT
            | ConditionType.SUBMISSION_INCORRECT
            | ConditionType.KEY_EVIDENCE_USED
            | ConditionType.DEDUCTION_CHAIN_COMPLETE
            | ConditionType.EVENT_TRIGGERED
            | ConditionType.EVENT_NOT_TRIGGERED
            | ConditionType.SESSION_COUNT
            | ConditionType.IS_FIRST_PLAY
            | ConditionType.HINT_COUNT_USED
        ):
            leaf = evaluate_leaf(condition, state)
            return ConditionEvaluation(value=leaf.value, trace=leaf.to_trace())
        case unreachable:
            assert_never(unreachable)


def _evaluate_all(
    condition: ConditionNode,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> ConditionEvaluation:
    # DSL §3.1 all：从左到右评估子条件，遇到第一个 false 立即短路。
    children: list[ConditionTraceNode] = []
    for child in condition.conditions:
        child_result = _evaluate(child, state, options)
        children.append(child_result.trace)
        if not child_result.value:
            return _logic_evaluation(condition.type, False, children)
    return _logic_evaluation(condition.type, True, children)


def _evaluate_any(
    condition: ConditionNode,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> ConditionEvaluation:
    # DSL §3.2 any：从左到右评估子条件，遇到第一个 true 立即短路。
    children: list[ConditionTraceNode] = []
    for child in condition.conditions:
        child_result = _evaluate(child, state, options)
        children.append(child_result.trace)
        if child_result.value:
            return _logic_evaluation(condition.type, True, children)
    return _logic_evaluation(condition.type, False, children)


def _evaluate_not(
    condition: ConditionNode,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> ConditionEvaluation:
    # DSL §3.3 not：只评估一个嵌套条件，并反转它的结果。
    if condition.condition is None:
        return _logic_evaluation(condition.type, True, [])
    child_result = _evaluate(condition.condition, state, options)
    return _logic_evaluation(condition.type, not child_result.value, [child_result.trace])


def _evaluate_count(
    condition: ConditionNode,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> ConditionEvaluation:
    # DSL §3.4 count：累计命中数达到 min 后立即短路返回 true。
    children: list[ConditionTraceNode] = []
    matched_count = 0
    minimum = condition.integer("min", 1)
    for child in condition.conditions:
        child_result = _evaluate(child, state, options)
        children.append(child_result.trace)
        if child_result.value:
            matched_count += 1
        if matched_count >= minimum:
            return _logic_evaluation(condition.type, True, children, f"{matched_count} matched")
    return _logic_evaluation(condition.type, False, children, f"{matched_count} matched")


def _logic_evaluation(
    condition_type: ConditionType,
    value: bool,
    children: list[ConditionTraceNode],
    detail: str | None = None,
) -> ConditionEvaluation:
    # DSL §7 trace 格式：组合节点必须保留已评估子节点，体现短路后的可见路径。
    return ConditionEvaluation(
        value=value,
        trace=ConditionTraceNode(
            label=condition_type.value,
            value=value,
            detail=detail,
            children=tuple(children),
        ),
    )


def _forced_result(
    condition: ConditionNode,
    options: ConditionEvaluationOptions,
) -> bool | None:
    # DSL §7 force_conditions：测试沙盒可在真实评估前覆盖某类条件结果。
    forced = options.force_conditions.get(condition.type.value)
    match forced:
        case "always_true":
            return True
        case "always_false":
            return False
        case None:
            return None


def _condition_cache_key(
    raw_condition: JsonMapping,
    state: GameState,
    options: ConditionEvaluationOptions,
) -> str:
    # DSL §5 缓存键 = hash(条件树 + 相关 GameState 片段)。
    # sort_keys/separators 生成稳定 JSON，避免同义 mapping 因插入顺序产生不同键。
    # force_conditions 会改变结果，也必须进入缓存键，防止调试覆盖污染正常评估。
    payload: JsonMapping = {
        "condition": raw_condition,
        "state": state_cache_snapshot(state),
        "force_conditions": options.force_conditions,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
