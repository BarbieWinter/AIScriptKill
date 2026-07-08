from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import JsonMapping


class ConditionType(StrEnum):
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


@dataclass(frozen=True, slots=True)
class ConditionDslError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True, slots=True)
class ConditionNode:
    type: ConditionType
    parameters: JsonMapping
    conditions: tuple["ConditionNode", ...] = ()
    condition: "ConditionNode | None" = None

    def text(self, key: str) -> str | None:
        value = self.parameters.get(key)
        if isinstance(value, str) and value != "":
            return value
        return None

    def required_text(self, key: str) -> str:
        value = self.text(key)
        if value is not None:
            return value
        raise ConditionDslError("CONDITION_FIELD_REQUIRED", f"{self.type.value}.{key} 必须是文本")

    def integer(self, key: str, default: int = 0) -> int:
        value = self.parameters.get(key)
        if isinstance(value, bool):
            return default
        if isinstance(value, int):
            return value
        return default

    def boolean(self, key: str, default: bool = False) -> bool:
        value = self.parameters.get(key)
        if isinstance(value, bool):
            return value
        return default

    def text_tuple(self, key: str) -> tuple[str, ...]:
        value = self.parameters.get(key)
        if not isinstance(value, list):
            return ()
        return tuple(item for item in value if isinstance(item, str) and item != "")


def parse_condition(raw: JsonMapping) -> ConditionNode:
    condition_type = _condition_type(raw.get("type"))
    parameters = _parameters(raw)
    match condition_type:
        case ConditionType.ALL | ConditionType.ANY | ConditionType.COUNT:
            return ConditionNode(
                type=condition_type,
                parameters=parameters,
                conditions=_child_conditions(raw.get("conditions"), condition_type),
            )
        case ConditionType.NOT:
            return ConditionNode(
                type=condition_type,
                parameters=parameters,
                condition=_single_condition(raw.get("condition"), condition_type),
            )
        case _:
            return ConditionNode(type=condition_type, parameters=parameters)


def _condition_type(value: JsonValue | None) -> ConditionType:
    if not isinstance(value, str):
        raise ConditionDslError("CONDITION_TYPE_REQUIRED", "condition.type 必须是文本")
    try:
        return ConditionType(value)
    except ValueError as exc:
        raise ConditionDslError("CONDITION_TYPE_INVALID", f"不支持的条件类型: {value}") from exc


def _parameters(raw: JsonMapping) -> JsonMapping:
    return {
        key: value
        for key, value in raw.items()
        if key not in {"condition", "conditions"} and isinstance(key, str)
    }


def _child_conditions(
    value: JsonValue | None,
    condition_type: ConditionType,
) -> tuple[ConditionNode, ...]:
    if not isinstance(value, list):
        raise ConditionDslError(
            "CONDITION_CHILDREN_REQUIRED",
            f"{condition_type.value}.conditions 必须是列表",
        )
    return tuple(parse_condition(item) for item in value if isinstance(item, dict))


def _single_condition(value: JsonValue | None, condition_type: ConditionType) -> ConditionNode:
    if isinstance(value, dict):
        return parse_condition(value)
    raise ConditionDslError(
        "CONDITION_CHILD_REQUIRED",
        f"{condition_type.value}.condition 必须是对象",
    )
