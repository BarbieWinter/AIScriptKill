from time import perf_counter

from engine.core.condition_evaluator import (
    ConditionEvaluationOptions,
    evaluate_condition,
    evaluate_condition_with_trace,
    format_condition_trace,
)
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


def test_evaluate_condition_cache_key_includes_state_snapshot() -> None:
    state = rich_state()
    state["unlocked_clues"] = []
    state["discovered_clues"] = []
    condition: JsonMapping = {"type": "clue_discovered", "clue_id": "clue_key"}

    first_result = evaluate_condition(condition, state)
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
    assert len(state["condition_cache"]) == 2


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
