"""规范化并比较条件叶子求值器使用的值。"""

from datetime import datetime

from engine.api.schemas.common import JsonValue
from engine.core.condition_models import ConditionDslError, ConditionNode
from engine.core.game_state import GameState, RuntimeScalar


def count_matches(count: int, minimum: int, maximum: int, exact: int) -> bool:
    """优先应用精确计数，否则检查闭区间计数范围。"""

    if exact >= 0:
        return count == exact
    return minimum <= count <= maximum


def compare_state_value(value: RuntimeScalar, threshold: int, comparison: str) -> bool:
    """应用 DSL 数值比较器，同时拒绝布尔值和文本。"""

    # DSL §2.3 的 threshold/comparison 只定义数值状态；bool 不能作为 0/1 参与比较。
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    match comparison:
        case "gte":
            return value >= threshold
        case "gt":
            return value > threshold
        case "lte":
            return value <= threshold
        case "lt":
            return value < threshold
        case "eq":
            return value == threshold
        case _:
            raise ConditionDslError(
                "CONDITION_FIELD_INVALID",
                "npc_state_reached.comparison 必须是 gte/gt/lte/lt/eq",
            )


def json_scalar_equal(left: JsonValue, right: JsonValue) -> bool:
    """比较 JSON 标量，且不把布尔值视为数值。"""

    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left is right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return left == right
    if isinstance(left, str) and isinstance(right, str):
        return left == right
    return left is None and right is None


def parse_time(value: str) -> datetime:
    """解析带时区偏移的 ISO 时间戳，否则抛出 CONDITION_TIME_INVALID。"""

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConditionDslError("CONDITION_TIME_INVALID", f"无效的 ISO 时间: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConditionDslError(
            "CONDITION_TIME_INVALID",
            f"ISO 时间必须包含 UTC offset: {value}",
        )
    return parsed


def optional_label(name: str, value: str | None) -> str:
    """将可选值追加到条件跟踪标签。"""

    if value is None:
        return name
    return f"{name}({value})"


def matching_clues(condition: ConditionNode, state: GameState) -> list[dict[str, JsonValue]]:
    """返回按可选轮次、场景和仅关键线索条件筛选的已发现线索。"""
    clues: list[dict[str, JsonValue]] = [
        {
            "clue_id": clue["clue_id"],
            "round_id": clue["round_id"],
            "scene_id": clue["scene_id"],
            "is_key": clue["is_key"],
        }
        for clue in state["discovered_clues"]
    ]
    round_id = condition.text("in_round")
    scene_id = condition.text("in_scene")
    if round_id is not None:
        clues = [clue for clue in clues if clue.get("round_id") == round_id]
    if scene_id is not None:
        clues = [clue for clue in clues if clue.get("scene_id") == scene_id]
    if condition.boolean("key_only"):
        clues = [clue for clue in clues if clue.get("is_key") is True]
    return clues


def submitted_key_evidence_ids(value: JsonValue | None) -> tuple[str, ...]:
    """从已提交的 JSON 值中提取字符串证物 ID。"""

    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def clues_label(condition: ConditionNode) -> str:
    """为 clues_discovered 条件构建稳定的跟踪标签。"""

    round_id = condition.text("in_round")
    minimum = condition.integer("min_count", 0)
    if round_id is not None:
        return f"clues_discovered({round_id}, min={minimum})"
    return f"clues_discovered(min={minimum})"
