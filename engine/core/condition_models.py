"""定义并校验递归条件 DSL 模型。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final, Literal

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping


class ConditionType(StrEnum):
    """枚举条件 DSL 支持的运算符。"""

    ALL = "all"
    ANY = "any"
    NOT = "not"
    COUNT = "count"
    ALWAYS = "always"
    NEVER = "never"
    STAGE_COMPLETED = "stage_completed"
    STAGE_REACHED = "stage_reached"
    ACT_COMPLETED = "act_completed"
    CLUES_DISCOVERED = "clues_discovered"
    CLUE_DISCOVERED = "clue_discovered"
    EVIDENCE_FOUND = "evidence_found"
    EVIDENCE_VIEWED = "evidence_viewed"
    CHARACTER_CHAPTER_READ = "character_chapter_read"
    EVIDENCE_SHOWN_TO_NPC = "evidence_shown_to_npc"
    CHARACTER_TALKED_TO = "character_talked_to"
    DIALOG_TRIGGERED = "dialog_triggered"
    PLAYER_SAID_KEYWORD = "player_said_keyword"
    NPC_STATE_REACHED = "npc_state_reached"
    PLAYER_ACTION_PERFORMED = "player_action_performed"
    PLAYER_REQUESTED = "player_requested"
    PLAYER_USED_CARD = "player_used_card"
    TIME_ELAPSED = "time_elapsed"
    REAL_TIME_REACHED = "real_time_reached"
    SUBMISSION_CORRECT = "submission_correct"
    SUBMISSION_INCORRECT = "submission_incorrect"
    KEY_EVIDENCE_USED = "key_evidence_used"
    DEDUCTION_CHAIN_COMPLETE = "deduction_chain_complete"
    EVENT_TRIGGERED = "event_triggered"
    EVENT_NOT_TRIGGERED = "event_not_triggered"
    SESSION_COUNT = "session_count"
    IS_FIRST_PLAY = "is_first_play"
    HINT_COUNT_USED = "hint_count_used"


ForceConditionResult = Literal["always_true", "always_false"]
LOGIC_CONDITION_TYPES: Final[frozenset[ConditionType]] = frozenset(
    (ConditionType.ALL, ConditionType.ANY, ConditionType.NOT, ConditionType.COUNT),
)
NUMERIC_COMPARISONS: Final[frozenset[str]] = frozenset(("gte", "gt", "lte", "lt", "eq"))
CARD_TYPES: Final[frozenset[str]] = frozenset(("skill", "prop"))
CONDITION_PARAMETER_KEYS: Final[dict[ConditionType, frozenset[str]]] = {
    ConditionType.ALL: frozenset(),
    ConditionType.ANY: frozenset(),
    ConditionType.NOT: frozenset(),
    ConditionType.COUNT: frozenset(("min",)),
    ConditionType.ALWAYS: frozenset(),
    ConditionType.NEVER: frozenset(),
    ConditionType.STAGE_COMPLETED: frozenset(("stage_id",)),
    ConditionType.STAGE_REACHED: frozenset(("stage_id",)),
    ConditionType.ACT_COMPLETED: frozenset(("act_id",)),
    ConditionType.CLUES_DISCOVERED: frozenset(
        ("in_round", "in_scene", "min_count", "max_count", "exact_count", "key_only"),
    ),
    ConditionType.CLUE_DISCOVERED: frozenset(("clue_id",)),
    ConditionType.EVIDENCE_FOUND: frozenset(("evidence_id",)),
    ConditionType.EVIDENCE_VIEWED: frozenset(("evidence_id",)),
    ConditionType.CHARACTER_CHAPTER_READ: frozenset(("chapter_id",)),
    ConditionType.EVIDENCE_SHOWN_TO_NPC: frozenset(("evidence_id", "character_id")),
    ConditionType.CHARACTER_TALKED_TO: frozenset(("character_id", "min_count")),
    ConditionType.DIALOG_TRIGGERED: frozenset(("dialog_id",)),
    ConditionType.PLAYER_SAID_KEYWORD: frozenset(("keyword", "case_sensitive")),
    ConditionType.NPC_STATE_REACHED: frozenset(
        ("character_id", "state", "threshold", "comparison"),
    ),
    ConditionType.PLAYER_ACTION_PERFORMED: frozenset(("action_id", "target")),
    ConditionType.PLAYER_REQUESTED: frozenset(("dialog_id",)),
    ConditionType.PLAYER_USED_CARD: frozenset(("card_id", "card_type")),
    ConditionType.TIME_ELAPSED: frozenset(("minutes", "since_stage_entry")),
    ConditionType.REAL_TIME_REACHED: frozenset(("time",)),
    ConditionType.SUBMISSION_CORRECT: frozenset(("field", "value")),
    ConditionType.SUBMISSION_INCORRECT: frozenset(("field", "value")),
    ConditionType.KEY_EVIDENCE_USED: frozenset(("min_count", "evidence_ids")),
    ConditionType.DEDUCTION_CHAIN_COMPLETE: frozenset(("chain_id",)),
    ConditionType.EVENT_TRIGGERED: frozenset(("event_id",)),
    ConditionType.EVENT_NOT_TRIGGERED: frozenset(("event_id",)),
    ConditionType.SESSION_COUNT: frozenset(("counter", "min", "max")),
    ConditionType.IS_FIRST_PLAY: frozenset(),
    ConditionType.HINT_COUNT_USED: frozenset(("min", "max")),
}


@dataclass(slots=True)
class ConditionDslError(Exception):
    """携带稳定校验码和便于阅读的 DSL 错误。"""

    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ConditionNode:
    """表示一个已校验的递归条件表达式。"""

    type: ConditionType
    parameters: JsonMapping
    conditions: tuple["ConditionNode", ...] = ()
    condition: "ConditionNode | None" = None

    def text(self, key: str, *, allow_none: bool = False) -> str | None:
        """读取可选的非空文本参数，否则抛出 DSL 错误。"""

        if key not in self.parameters:
            return None
        value = self.parameters[key]
        if value is None and allow_none:
            return None
        if isinstance(value, str) and value != "":
            return value
        raise self.invalid_field(key, "非空文本")

    def required_text(self, key: str) -> str:
        """读取必需的非空文本参数，否则抛出 DSL 错误。"""

        if key not in self.parameters:
            raise ConditionDslError(
                "CONDITION_FIELD_REQUIRED",
                f"{self.type.value}.{key} 必须是文本",
            )
        value = self.parameters[key]
        if isinstance(value, str) and value != "":
            return value
        raise self.invalid_field(key, "非空文本")

    def integer(self, key: str, default: int = 0) -> int:
        """读取整数参数，同时拒绝布尔值。"""

        if key not in self.parameters:
            return default
        value = self.parameters.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise self.invalid_field(key, "整数")

    def required_integer(self, key: str) -> int:
        """读取必需的整数参数，否则抛出 DSL 错误。"""

        if key not in self.parameters:
            raise ConditionDslError(
                "CONDITION_FIELD_REQUIRED",
                f"{self.type.value}.{key} 必须是整数",
            )
        return self.integer(key)

    def nonnegative_integer(self, key: str, default: int = 0) -> int:
        """读取值不小于零的整数参数。"""

        value = self.integer(key, default)
        if value < 0:
            raise self.invalid_field(key, "非负整数")
        return value

    def boolean(self, key: str, default: bool = False) -> bool:
        """读取布尔参数，缺失时返回给定默认值。"""

        if key not in self.parameters:
            return default
        value = self.parameters.get(key)
        if isinstance(value, bool):
            return value
        raise self.invalid_field(key, "布尔值")

    def required_scalar(self, key: str) -> str | int | float | bool:
        """读取必需的 JSON 标量，同时拒绝 null 和容器。"""

        if key not in self.parameters:
            raise ConditionDslError(
                "CONDITION_FIELD_REQUIRED",
                f"{self.type.value}.{key} 必须是非 null JSON 标量",
            )
        value = self.parameters[key]
        if isinstance(value, str | int | float | bool):
            return value
        raise self.invalid_field(key, "非 null JSON 标量")

    def text_tuple(self, key: str) -> tuple[str, ...]:
        """将可选的非空字符串列表读取为不可变元组。"""

        if key not in self.parameters:
            return ()
        value = self.parameters.get(key)
        if not isinstance(value, list):
            raise self.invalid_field(key, "非空文本列表")
        items: list[str] = []
        for item in value:
            if not isinstance(item, str) or item == "":
                raise self.invalid_field(key, "非空文本列表")
            items.append(item)
        return tuple(items)

    def invalid_field(self, key: str, expected: str) -> ConditionDslError:
        """为无效参数值构建稳定错误。"""

        return ConditionDslError(
            "CONDITION_FIELD_INVALID",
            f"{self.type.value}.{key} 必须是{expected}",
        )


def parse_condition(raw: JsonMapping) -> ConditionNode:
    """将一个 JSON 映射解析为完整校验的条件树。"""

    condition_type = _condition_type(raw.get("type"))
    _validate_raw_keys(raw, condition_type)
    parameters = _parameters(raw)
    match condition_type:
        case ConditionType.ALL | ConditionType.ANY | ConditionType.COUNT:
            node = ConditionNode(
                type=condition_type,
                parameters=parameters,
                conditions=_child_conditions(raw.get("conditions"), condition_type),
            )
        case ConditionType.NOT:
            node = ConditionNode(
                type=condition_type,
                parameters=parameters,
                condition=_single_condition(raw.get("condition"), condition_type),
            )
        case _:
            node = ConditionNode(type=condition_type, parameters=parameters)
    validate_condition_parameters(node)
    return node


def _validate_raw_keys(raw: JsonMapping, condition_type: ConditionType) -> None:
    structure_keys: frozenset[str]
    match condition_type:
        case ConditionType.ALL | ConditionType.ANY | ConditionType.COUNT:
            structure_keys = frozenset(("conditions",))
        case ConditionType.NOT:
            structure_keys = frozenset(("condition",))
        case _:
            structure_keys = frozenset()
    allowed = CONDITION_PARAMETER_KEYS[condition_type] | structure_keys | {"type"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ConditionDslError(
            "CONDITION_FIELD_INVALID",
            f"{condition_type.value} 不支持参数: {unknown[0]}",
        )


def validate_condition_parameters(condition: ConditionNode) -> None:
    """拒绝缺失、未知或语义无效的运算符参数。"""

    _validate_known_parameters(condition)
    match condition.type:
        case ConditionType.ALL | ConditionType.ANY | ConditionType.NOT:
            return
        case ConditionType.COUNT:
            minimum = condition.required_integer("min")
            if minimum < 0:
                raise condition.invalid_field("min", "非负整数")
        case ConditionType.ALWAYS | ConditionType.NEVER | ConditionType.IS_FIRST_PLAY:
            return
        case ConditionType.STAGE_COMPLETED | ConditionType.STAGE_REACHED:
            condition.required_text("stage_id")
        case ConditionType.ACT_COMPLETED:
            condition.required_text("act_id")
        case ConditionType.CLUES_DISCOVERED:
            condition.text("in_round")
            condition.text("in_scene")
            condition.nonnegative_integer("min_count")
            condition.nonnegative_integer("max_count")
            if "exact_count" in condition.parameters:
                condition.nonnegative_integer("exact_count")
            condition.boolean("key_only", False)
        case ConditionType.CLUE_DISCOVERED:
            condition.required_text("clue_id")
        case ConditionType.EVIDENCE_FOUND | ConditionType.EVIDENCE_VIEWED:
            condition.required_text("evidence_id")
        case ConditionType.CHARACTER_CHAPTER_READ:
            condition.required_text("chapter_id")
        case ConditionType.EVIDENCE_SHOWN_TO_NPC:
            condition.required_text("evidence_id")
            condition.required_text("character_id")
        case ConditionType.CHARACTER_TALKED_TO:
            condition.required_text("character_id")
            condition.nonnegative_integer("min_count", 1)
        case ConditionType.DIALOG_TRIGGERED:
            condition.required_text("dialog_id")
        case ConditionType.PLAYER_SAID_KEYWORD:
            condition.required_text("keyword")
            condition.boolean("case_sensitive", False)
        case ConditionType.NPC_STATE_REACHED:
            condition.required_text("character_id")
            condition.required_text("state")
            condition.integer("threshold", 0)
            _validate_optional_choice(condition, "comparison", NUMERIC_COMPARISONS)
        case ConditionType.PLAYER_ACTION_PERFORMED:
            condition.required_text("action_id")
            condition.text("target", allow_none=True)
        case ConditionType.PLAYER_REQUESTED:
            condition.text("dialog_id")
        case ConditionType.PLAYER_USED_CARD:
            condition.text("card_id")
            _validate_optional_choice(condition, "card_type", CARD_TYPES)
        case ConditionType.TIME_ELAPSED:
            condition.nonnegative_integer("minutes")
            if not condition.boolean("since_stage_entry", True):
                raise ConditionDslError(
                    "CONDITION_FIELD_INVALID",
                    "time_elapsed.since_stage_entry 当前只支持 true",
                )
        case ConditionType.REAL_TIME_REACHED:
            _validate_aware_iso_time(condition)
        case ConditionType.SUBMISSION_CORRECT | ConditionType.SUBMISSION_INCORRECT:
            condition.required_text("field")
            if "value" in condition.parameters:
                condition.required_scalar("value")
        case ConditionType.KEY_EVIDENCE_USED:
            condition.nonnegative_integer("min_count", 1)
            condition.text_tuple("evidence_ids")
        case ConditionType.DEDUCTION_CHAIN_COMPLETE:
            condition.required_text("chain_id")
        case ConditionType.EVENT_TRIGGERED | ConditionType.EVENT_NOT_TRIGGERED:
            condition.required_text("event_id")
        case ConditionType.SESSION_COUNT:
            condition.required_text("counter")
            minimum = condition.nonnegative_integer("min")
            maximum = condition.nonnegative_integer("max")
            if "max" in condition.parameters and maximum < minimum:
                raise condition.invalid_field("max", "不小于 min 的非负整数")
        case ConditionType.HINT_COUNT_USED:
            minimum = condition.nonnegative_integer("min")
            maximum = condition.nonnegative_integer("max")
            if "max" in condition.parameters and maximum < minimum:
                raise condition.invalid_field("max", "不小于 min 的非负整数")


def _validate_aware_iso_time(condition: ConditionNode) -> None:
    value = condition.required_text("time")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ConditionDslError("CONDITION_TIME_INVALID", f"无效的 ISO 时间: {value}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ConditionDslError(
            "CONDITION_TIME_INVALID",
            f"ISO 时间必须包含 UTC offset: {value}",
        )


def _validate_optional_choice(
    condition: ConditionNode,
    key: str,
    allowed: frozenset[str],
) -> None:
    value = condition.text(key)
    if value is not None and value not in allowed:
        choices = "/".join(sorted(allowed))
        raise ConditionDslError(
            "CONDITION_FIELD_INVALID",
            f"{condition.type.value}.{key} 必须是 {choices}",
        )


def _validate_known_parameters(condition: ConditionNode) -> None:
    allowed = CONDITION_PARAMETER_KEYS[condition.type] | {"type"}
    unknown = sorted(set(condition.parameters) - allowed)
    if unknown:
        raise ConditionDslError(
            "CONDITION_FIELD_INVALID",
            f"{condition.type.value} 不支持参数: {unknown[0]}",
        )


def _condition_type(value: JsonValue | None) -> ConditionType:
    if not isinstance(value, str):
        raise ConditionDslError("CONDITION_TYPE_REQUIRED", "condition.type 必须是文本")
    try:
        return ConditionType(value)
    except ValueError as exc:
        raise ConditionDslError("CONDITION_TYPE_INVALID", f"不支持的条件类型: {value}") from exc


def _parameters(raw: JsonMapping) -> JsonMapping:
    return {key: value for key, value in raw.items() if key not in {"condition", "conditions"}}


def _child_conditions(
    value: JsonValue | None,
    condition_type: ConditionType,
) -> tuple[ConditionNode, ...]:
    if not isinstance(value, list):
        raise ConditionDslError(
            "CONDITION_CHILDREN_REQUIRED",
            f"{condition_type.value}.conditions 必须是列表",
        )
    children: list[ConditionNode] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ConditionDslError(
                "CONDITION_CHILD_INVALID",
                f"{condition_type.value}.conditions[{index}] 必须是对象",
            )
        children.append(parse_condition(item))
    return tuple(children)


def _single_condition(value: JsonValue | None, condition_type: ConditionType) -> ConditionNode:
    if isinstance(value, dict):
        return parse_condition(value)
    raise ConditionDslError(
        "CONDITION_CHILD_REQUIRED",
        f"{condition_type.value}.condition 必须是对象",
    )
