from contextlib import contextmanager
from time import perf_counter
from typing import Generator

import pytest

from engine.api.schemas.common import JsonValue
from engine.core.condition_evaluator import (
    ConditionEvaluationOptions,
    evaluate_condition,
    evaluate_condition_with_trace,
    format_condition_trace,
)
from engine.core.condition_models import ConditionDslError
from engine.core.game_state import RuntimeScalar
from engine.core.package_schema import JsonMapping
from engine.tests.condition_evaluator_fixtures import (
    leaf_condition_cases,
    logic_condition_cases,
    rich_state,
)


def test_evaluate_condition_handles_every_documented_leaf_type() -> None:
    state = rich_state()

    for condition, expected in leaf_condition_cases():
        assert evaluate_condition(condition, state) is expected


def test_evaluate_condition_handles_is_first_play_false_case() -> None:
    state = rich_state()
    state["is_first_play"] = False

    assert evaluate_condition({"type": "is_first_play"}, state) is False


def test_condition_dsl_error_propagates_through_contextmanager() -> None:
    @contextmanager
    def evaluation_boundary() -> Generator[None, None, None]:
        yield

    with pytest.raises(ConditionDslError) as exc_info:
        with evaluation_boundary():
            evaluate_condition({"type": "time_elapsed", "minutes": "20"}, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_submission_incorrect_with_explicit_value_matches_only_that_wrong_value() -> None:
    state = rich_state()
    condition: JsonMapping = {
        "type": "submission_incorrect",
        "field": "suspect",
        "value": "wangdada",
    }

    state["final_submission"] = {"suspect": "wangdada"}
    assert evaluate_condition(condition, state) is True

    state["final_submission"] = {"suspect": "another_suspect"}
    assert evaluate_condition(condition, state) is False

    state["final_submission"] = {"suspect": "chengjun"}
    assert evaluate_condition(condition, state) is False


def test_submission_incorrect_without_explicit_value_uses_answer_key() -> None:
    state = rich_state()
    condition: JsonMapping = {"type": "submission_incorrect", "field": "suspect"}

    state["final_submission"] = {"suspect": "wangdada"}
    assert evaluate_condition(condition, state) is True

    state["final_submission"] = {"suspect": "chengjun"}
    assert evaluate_condition(condition, state) is False


@pytest.mark.parametrize("condition_type", ["submission_correct", "submission_incorrect"])
@pytest.mark.parametrize("explicit_value", [False, True])
def test_submission_conditions_require_the_submitted_field(
    condition_type: str,
    explicit_value: bool,
) -> None:
    condition: JsonMapping = {"type": condition_type, "field": "suspect"}
    if explicit_value:
        condition["value"] = "wangdada"

    state = rich_state()
    state["final_submission"] = None
    assert evaluate_condition(condition, state) is False

    state["final_submission"] = {"motive": "revenge"}
    assert evaluate_condition(condition, state) is False


@pytest.mark.parametrize("condition_type", ["submission_correct", "submission_incorrect"])
def test_implicit_submission_conditions_require_answer_key_field(condition_type: str) -> None:
    state = rich_state()
    state["final_submission"] = {"suspect": "wangdada"}
    state["answer_key"] = {}

    assert evaluate_condition({"type": condition_type, "field": "suspect"}, state) is False


@pytest.mark.parametrize("condition_type", ["submission_correct", "submission_incorrect"])
@pytest.mark.parametrize("invalid_value", [None, ["chengjun"], {"id": "chengjun"}])
def test_submission_conditions_reject_non_scalar_explicit_value(
    condition_type: str,
    invalid_value: JsonValue,
) -> None:
    condition: JsonMapping = {
        "type": condition_type,
        "field": "suspect",
        "value": invalid_value,
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"

    state_without_submission = rich_state()
    state_without_submission["final_submission"] = None
    with pytest.raises(ConditionDslError) as missing_submission_error:
        evaluate_condition(condition, state_without_submission)

    assert missing_submission_error.value.code == "CONDITION_FIELD_INVALID"


@pytest.mark.parametrize(
    ("condition_type", "submitted_value", "expected_value", "expected_result"),
    [
        ("submission_correct", True, 1, False),
        ("submission_correct", 1, True, False),
        ("submission_incorrect", True, 1, False),
        ("submission_incorrect", 1, True, False),
        ("submission_correct", 1, 1.0, True),
        ("submission_incorrect", 1.0, 1, True),
    ],
)
def test_submission_conditions_use_json_scalar_equality(
    condition_type: str,
    submitted_value: JsonValue,
    expected_value: JsonValue,
    expected_result: bool,
) -> None:
    state = rich_state()
    state["final_submission"] = {"suspect": submitted_value}
    condition: JsonMapping = {
        "type": condition_type,
        "field": "suspect",
        "value": expected_value,
    }

    assert evaluate_condition(condition, state) is expected_result


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "time_elapsed", "minutes": "20"},
        {"type": "time_elapsed", "minutes": True},
        {"type": "count", "min": "2", "conditions": [{"type": "always"}]},
        {"type": "player_said_keyword", "keyword": "clue", "case_sensitive": "false"},
        {"type": "player_requested", "dialog_id": 7},
    ],
)
def test_evaluate_condition_rejects_explicit_invalid_scalar_fields(
    condition: JsonMapping,
) -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_required_text_distinguishes_missing_from_explicit_invalid_value() -> None:
    with pytest.raises(ConditionDslError) as missing_error:
        evaluate_condition({"type": "stage_completed"}, rich_state())
    assert missing_error.value.code == "CONDITION_FIELD_REQUIRED"

    for invalid_value in (None, 7, ""):
        with pytest.raises(ConditionDslError) as invalid_error:
            evaluate_condition(
                {"type": "stage_completed", "stage_id": invalid_value},
                rich_state(),
            )
        assert invalid_error.value.code == "CONDITION_FIELD_INVALID"


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "time_elapsed"},
        {"type": "count", "conditions": [{"type": "always"}]},
    ],
)
def test_required_integer_fields_reject_missing_value(condition: JsonMapping) -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_REQUIRED"


@pytest.mark.parametrize("conditions", [[], [{"type": "never"}]])
def test_count_min_zero_short_circuits_without_evaluating_children(
    conditions: list[JsonValue],
) -> None:
    # 给定：至少命中零项的 count，子树为空或包含未命中条件。
    condition: JsonMapping = {"type": "count", "min": 0, "conditions": conditions}

    # 当：求值器生成带跟踪的结果。
    result = evaluate_condition_with_trace(condition, rich_state())

    # 则：结果立即为真，且跟踪中没有被访问的子节点。
    assert result.value is True
    assert result.trace.children == ()


def test_optional_text_rejects_null_except_documented_action_target() -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition({"type": "player_requested", "dialog_id": None}, rich_state())
    assert exc_info.value.code == "CONDITION_FIELD_INVALID"

    assert (
        evaluate_condition(
            {"type": "player_action_performed", "action_id": "use_card", "target": None},
            rich_state(),
        )
        is True
    )


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "key_evidence_used", "evidence_ids": "bloody_knife"},
        {"type": "key_evidence_used", "evidence_ids": ["bloody_knife", 7]},
        {"type": "key_evidence_used", "evidence_ids": ["bloody_knife", ""]},
    ],
)
def test_evaluate_condition_rejects_malformed_text_lists(condition: JsonMapping) -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_evaluate_condition_rejects_non_object_logic_child() -> None:
    condition: JsonMapping = {
        "type": "all",
        "conditions": [{"type": "always"}, "malformed"],
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_CHILD_INVALID"


@pytest.mark.parametrize(
    ("condition", "options", "expected_code"),
    [
        (
            {
                "type": "all",
                "conditions": [
                    {"type": "never"},
                    {"type": "time_elapsed", "minutes": "20"},
                ],
            },
            None,
            "CONDITION_FIELD_INVALID",
        ),
        (
            {
                "type": "any",
                "conditions": [
                    {"type": "always"},
                    {
                        "type": "player_said_keyword",
                        "keyword": "clue",
                        "case_sensitive": "false",
                    },
                ],
            },
            None,
            "CONDITION_FIELD_INVALID",
        ),
        (
            {"type": "time_elapsed", "minutes": "20"},
            ConditionEvaluationOptions(force_conditions={"time_elapsed": "always_true"}),
            "CONDITION_FIELD_INVALID",
        ),
    ],
)
def test_evaluate_condition_validates_complete_tree_before_execution(
    condition: JsonMapping,
    options: ConditionEvaluationOptions | None,
    expected_code: str,
) -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state(), options)

    assert exc_info.value.code == expected_code


def test_evaluate_condition_rejects_misspelled_optional_parameter() -> None:
    condition: JsonMapping = {
        "type": "any",
        "conditions": [
            {"type": "always"},
            {
                "type": "player_said_keyword",
                "keyword": "clue",
                "case_sensitiv": False,
            },
        ],
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"
    assert "case_sensitiv" in exc_info.value.message


def test_evaluate_condition_rejects_unknown_logic_parameter() -> None:
    condition: JsonMapping = {
        "type": "all",
        "min": 1,
        "conditions": [{"type": "always"}],
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"
    assert "min" in exc_info.value.message


@pytest.mark.parametrize(
    "condition",
    [
        {"type": "always", "conditions": []},
        {"type": "all", "conditions": [{"type": "always"}], "condition": {"type": "never"}},
        {"type": "not", "condition": {"type": "never"}, "conditions": []},
    ],
)
def test_evaluate_condition_rejects_structure_key_for_wrong_node_type(
    condition: JsonMapping,
) -> None:
    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_time_elapsed_rejects_unsupported_session_wide_timer() -> None:
    condition: JsonMapping = {
        "type": "time_elapsed",
        "minutes": 20,
        "since_stage_entry": False,
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_npc_state_reached_rejects_unknown_numeric_comparison() -> None:
    condition: JsonMapping = {
        "type": "npc_state_reached",
        "character_id": "wangdada",
        "state": "fear",
        "threshold": 50,
        "comparison": "approximately",
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_npc_state_reached_validates_comparison_before_state_lookup() -> None:
    condition: JsonMapping = {
        "type": "npc_state_reached",
        "character_id": "ghost",
        "state": "missing",
        "comparison": "approximately",
    }

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


@pytest.mark.parametrize("state_value", ["nervous", True, None])
def test_npc_state_reached_returns_false_for_non_numeric_state(
    state_value: RuntimeScalar,
) -> None:
    state = rich_state()
    state["npc_states"]["wangdada"]["mood"] = state_value
    condition: JsonMapping = {
        "type": "npc_state_reached",
        "character_id": "wangdada",
        "state": "mood",
        "threshold": 0,
        "comparison": "gte",
    }

    assert evaluate_condition(condition, state) is False


def test_player_used_card_rejects_unknown_card_type() -> None:
    condition: JsonMapping = {"type": "player_used_card", "card_type": "magic"}

    with pytest.raises(ConditionDslError) as exc_info:
        evaluate_condition(condition, rich_state())

    assert exc_info.value.code == "CONDITION_FIELD_INVALID"


def test_evaluate_condition_handles_logic_nodes_and_short_circuit_trace() -> None:
    state = rich_state()
    condition: JsonMapping = {
        "type": "all",
        "conditions": [
            {"type": "never"},
            {"type": "clue_discovered", "clue_id": "clue_key"},
        ],
    }

    result = evaluate_condition_with_trace(condition, state)

    assert result.value is False
    assert [node.label for node in result.trace.children] == ["never"]


def test_clue_discovered_requires_discovery_record_instead_of_unlock() -> None:
    # 给定：线索已解锁，但玩家尚未发现该线索。
    state = rich_state()
    state["unlocked_clues"] = ["clue_key"]
    state["discovered_clues"] = []
    condition: JsonMapping = {"type": "clue_discovered", "clue_id": "clue_key"}

    # 当/则：解锁状态不能让“已发现”条件提前成立。
    assert evaluate_condition(condition, state) is False


def test_evaluate_condition_handles_logic_type_true_and_false_cases() -> None:
    state = rich_state()

    for condition, expected in logic_condition_cases():
        assert evaluate_condition(condition, state) is expected


def test_evaluate_condition_handles_five_level_nested_tree() -> None:
    state = rich_state()
    condition: JsonMapping = {
        "type": "all",
        "conditions": [
            {
                "type": "not",
                "condition": {
                    "type": "any",
                    "conditions": [
                        {"type": "never"},
                        {
                            "type": "count",
                            "min": 2,
                            "conditions": [
                                {"type": "always"},
                                {"type": "clue_discovered", "clue_id": "clue_key"},
                                {"type": "event_not_triggered", "event_id": "broadcast_1"},
                            ],
                        },
                    ],
                },
            }
        ],
    }

    assert evaluate_condition(condition, state) is False


def test_evaluate_condition_cache_drops_previous_state_snapshot() -> None:
    state = rich_state()
    state["unlocked_clues"] = []
    state["discovered_clues"] = []
    condition: JsonMapping = {"type": "clue_discovered", "clue_id": "clue_key"}

    first_result = evaluate_condition(condition, state)
    first_key = next(iter(state["condition_cache"]))
    state["unlocked_clues"] = ["clue_key"]
    state["discovered_clues"] = [
        {
            "clue_id": "clue_key",
            "round_id": "act1_round1",
            "scene_id": "crime_scene",
            "is_key": True,
        }
    ]
    second_result = evaluate_condition(condition, state)

    assert first_result is False
    assert second_result is True
    assert len(state["condition_cache"]) == 1
    assert next(iter(state["condition_cache"])) != first_key


def test_evaluate_condition_reuses_cache_for_same_snapshot_and_options() -> None:
    state = rich_state()
    condition: JsonMapping = {"type": "clue_discovered", "clue_id": "clue_key"}

    assert evaluate_condition(condition, state) is True
    cache_key = next(iter(state["condition_cache"]))
    state["condition_cache"][cache_key] = False

    assert evaluate_condition(condition, state) is False
    assert len(state["condition_cache"]) == 1


def test_evaluate_condition_cache_drops_previous_force_options() -> None:
    state = rich_state()
    condition: JsonMapping = {"type": "never"}
    force_true = ConditionEvaluationOptions(force_conditions={"never": "always_true"})
    force_false = ConditionEvaluationOptions(force_conditions={"never": "always_false"})

    assert evaluate_condition(condition, state, force_true) is True
    first_key = next(iter(state["condition_cache"]))
    assert evaluate_condition(condition, state, force_false) is False

    assert len(state["condition_cache"]) == 1
    assert next(iter(state["condition_cache"])) != first_key


def test_format_condition_trace_matches_documented_shape() -> None:
    state = rich_state()
    condition: JsonMapping = {
        "type": "any",
        "conditions": [
            {
                "type": "all",
                "conditions": [
                    {"type": "clues_discovered", "in_round": "act1_round1", "min_count": 3},
                    {"type": "character_talked_to", "character_id": "ghost"},
                ],
            },
            {"type": "player_requested", "dialog_id": "move_on"},
            {"type": "time_elapsed", "minutes": 30},
        ],
    }

    result = evaluate_condition_with_trace(condition, state)
    trace_text = format_condition_trace("stage_exit_check for act1_investigation", result)

    assert trace_text.splitlines() == [
        "[Condition Trace] stage_exit_check for act1_investigation:",
        "  ├─ any: FALSE",
        "  │  ├─ all: FALSE",
        "  │  │  ├─ clues_discovered(act1_round1, min=3): TRUE (3 found)",
        "  │  │  └─ character_talked_to(ghost): FALSE (0 talks)",
        "  │  ├─ player_requested(move_on): FALSE",
        "  │  └─ time_elapsed(min=30): FALSE (elapsed 25min)",
        "  └─ Result: FALSE",
    ]


def test_evaluate_condition_honors_debug_force_conditions() -> None:
    state = rich_state()
    condition: JsonMapping = {"type": "never"}
    options = ConditionEvaluationOptions(force_conditions={"never": "always_true"})

    assert evaluate_condition(condition, state, options) is True


def test_evaluate_condition_tree_with_one_hundred_conditions_under_ten_ms() -> None:
    state = rich_state()
    condition: JsonMapping = {
        "type": "all",
        "conditions": [{"type": "clue_discovered", "clue_id": "clue_key"} for _ in range(100)],
    }

    started_at = perf_counter()
    result = evaluate_condition(condition, state)
    elapsed = perf_counter() - started_at

    assert result is True
    assert elapsed < 0.010
