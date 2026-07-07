from datetime import datetime

from engine.api.schemas.common import JsonValue
from engine.core.condition_models import ConditionDslError, ConditionNode
from engine.core.game_state import GameState, RuntimeScalar


def count_matches(count: int, minimum: int, maximum: int, exact: int) -> bool:
    if exact >= 0:
        return count == exact
    return minimum <= count <= maximum


def compare_state_value(value: RuntimeScalar, threshold: int, comparison: str) -> bool:
    if isinstance(value, str):
        return value == comparison
    if not isinstance(value, int | float):
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
            return False


def parse_time(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConditionDslError("CONDITION_TIME_INVALID", f"无效的 ISO 时间: {value}") from exc


def optional_label(name: str, value: str | None) -> str:
    if value is None:
        return name
    return f"{name}({value})"


def matching_clues(condition: ConditionNode, state: GameState) -> list[dict[str, JsonValue]]:
    clues: list[dict[str, JsonValue]] = [dict(clue) for clue in state["discovered_clues"]]
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
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def clues_label(condition: ConditionNode) -> str:
    round_id = condition.text("in_round")
    minimum = condition.integer("min_count", 0)
    if round_id is not None:
        return f"clues_discovered({round_id}, min={minimum})"
    return f"clues_discovered(min={minimum})"
