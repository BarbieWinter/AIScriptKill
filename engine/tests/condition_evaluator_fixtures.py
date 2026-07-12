from engine.core.game_state import GameState, create_initial_state
from engine.core.package_schema import JsonMapping


def rich_state() -> GameState:
    state = create_initial_state(
        session_id="session-1",
        script_id="minimal-case",
        player_id="player-1",
        player_character_id="detective",
        entry_stage="act2_intro",
    )
    state["stage_entered_at"] = "2026-07-05T20:40:00+08:00"
    state["current_time"] = "2026-07-05T21:05:00+08:00"
    state["completed_stages"] = ["prologue", "act1_intro"]
    state["completed_acts"] = ["book1"]
    state["unlocked_clues"] = ["clue_key", "clue_minor", "clue_scene2"]
    state["discovered_clues"] = [
        {
            "clue_id": "clue_key",
            "round_id": "act1_round1",
            "scene_id": "crime_scene",
            "is_key": True,
        },
        {
            "clue_id": "clue_minor",
            "round_id": "act1_round1",
            "scene_id": "crime_scene",
            "is_key": False,
        },
        {
            "clue_id": "clue_extra",
            "round_id": "act1_round1",
            "scene_id": "crime_scene",
            "is_key": False,
        },
        {
            "clue_id": "clue_scene2",
            "round_id": "act2_round1",
            "scene_id": "yard",
            "is_key": True,
        },
    ]
    state["discovered_evidences"] = ["bloody_knife"]
    state["evidences_shown_to_npcs"] = [{"evidence_id": "bloody_knife", "character_id": "wangdada"}]
    state["character_dialog_counts"] = {"wangdada": 3}
    state["triggered_dialogs"] = ["letter_sender"]
    state["player_utterances"] = ["我发现了李白留下的线索"]
    state["npc_states"] = {"wangdada": {"mood": "nervous", "fear": 60}}
    state["performed_actions"] = [{"action_id": "use_card", "target": "door"}]
    state["player_requests"] = ["i_want_to_move_on"]
    state["used_cards"] = [{"card_id": "interrogation_card", "card_type": "skill"}]
    state["final_submission"] = {
        "suspect": "chengjun",
        "motive": "revenge",
        "key_evidences": ["bloody_knife", "threatening_letter", "alibi_hole"],
    }
    state["answer_key"] = {"suspect": "chengjun", "motive": "revenge"}
    state["deduction_chains_completed"] = ["main"]
    state["completed_events"] = ["broadcast_1"]
    state["session_counters"] = {"wrong_submissions": 3}
    state["is_first_play"] = True
    state["hint_count"] = 2
    return state


def leaf_condition_cases() -> tuple[tuple[JsonMapping, bool], ...]:
    return (
        ({"type": "stage_completed", "stage_id": "act1_intro"}, True),
        ({"type": "stage_completed", "stage_id": "act3"}, False),
        ({"type": "stage_reached", "stage_id": "act2_intro"}, True),
        ({"type": "stage_reached", "stage_id": "act3"}, False),
        ({"type": "act_completed", "act_id": "book1"}, True),
        ({"type": "act_completed", "act_id": "book2"}, False),
        ({"type": "clues_discovered", "in_round": "act1_round1", "min_count": 2}, True),
        ({"type": "clues_discovered", "in_round": "act1_round1", "exact_count": 4}, False),
        ({"type": "clue_discovered", "clue_id": "clue_key"}, True),
        ({"type": "clue_discovered", "clue_id": "missing_clue"}, False),
        ({"type": "evidence_found", "evidence_id": "bloody_knife"}, True),
        ({"type": "evidence_found", "evidence_id": "missing_evidence"}, False),
        (
            {
                "type": "evidence_shown_to_npc",
                "evidence_id": "bloody_knife",
                "character_id": "wangdada",
            },
            True,
        ),
        (
            {
                "type": "evidence_shown_to_npc",
                "evidence_id": "bloody_knife",
                "character_id": "ghost",
            },
            False,
        ),
        ({"type": "character_talked_to", "character_id": "wangdada", "min_count": 3}, True),
        ({"type": "character_talked_to", "character_id": "wangdada", "min_count": 4}, False),
        ({"type": "dialog_triggered", "dialog_id": "letter_sender"}, True),
        ({"type": "dialog_triggered", "dialog_id": "missing_dialog"}, False),
        ({"type": "player_said_keyword", "keyword": "李白"}, True),
        ({"type": "player_said_keyword", "keyword": "missing"}, False),
        (
            {
                "type": "npc_state_reached",
                "character_id": "wangdada",
                "state": "fear",
                "threshold": 50,
                "comparison": "gte",
            },
            True,
        ),
        (
            {
                "type": "npc_state_reached",
                "character_id": "wangdada",
                "state": "fear",
                "threshold": 80,
                "comparison": "gte",
            },
            False,
        ),
        ({"type": "player_action_performed", "action_id": "use_card", "target": "door"}, True),
        ({"type": "player_action_performed", "action_id": "show_evidence"}, False),
        ({"type": "player_requested", "dialog_id": "i_want_to_move_on"}, True),
        ({"type": "player_requested", "dialog_id": "missing_request"}, False),
        ({"type": "player_used_card", "card_id": "interrogation_card"}, True),
        ({"type": "player_used_card", "card_type": "prop"}, False),
        ({"type": "time_elapsed", "minutes": 20, "since_stage_entry": True}, True),
        ({"type": "time_elapsed", "minutes": 40, "since_stage_entry": True}, False),
        ({"type": "real_time_reached", "time": "2026-07-05T21:00:00+08:00"}, True),
        ({"type": "real_time_reached", "time": "2026-07-05T22:00:00+08:00"}, False),
        ({"type": "submission_correct", "field": "suspect", "value": "chengjun"}, True),
        ({"type": "submission_correct", "field": "suspect", "value": "wangdada"}, False),
        ({"type": "submission_incorrect", "field": "suspect", "value": "wangdada"}, False),
        ({"type": "submission_incorrect", "field": "suspect"}, False),
        ({"type": "key_evidence_used", "min_count": 3}, True),
        ({"type": "key_evidence_used", "evidence_ids": ["missing_evidence"]}, False),
        ({"type": "deduction_chain_complete", "chain_id": "main"}, True),
        ({"type": "deduction_chain_complete", "chain_id": "side"}, False),
        ({"type": "event_triggered", "event_id": "broadcast_1"}, True),
        ({"type": "event_triggered", "event_id": "missing_event"}, False),
        ({"type": "event_not_triggered", "event_id": "true_final_reveal"}, True),
        ({"type": "event_not_triggered", "event_id": "broadcast_1"}, False),
        ({"type": "session_count", "counter": "wrong_submissions", "min": 2, "max": 5}, True),
        ({"type": "session_count", "counter": "wrong_submissions", "max": 1}, False),
        ({"type": "is_first_play"}, True),
        ({"type": "hint_count_used", "min": 1, "max": 3}, True),
        ({"type": "hint_count_used", "max": 1}, False),
    )


def logic_condition_cases() -> tuple[tuple[JsonMapping, bool], ...]:
    return (
        (
            {
                "type": "all",
                "conditions": [
                    {"type": "always"},
                    {"type": "clue_discovered", "clue_id": "clue_key"},
                ],
            },
            True,
        ),
        ({"type": "all", "conditions": [{"type": "always"}, {"type": "never"}]}, False),
        (
            {
                "type": "any",
                "conditions": [
                    {"type": "never"},
                    {"type": "clue_discovered", "clue_id": "clue_key"},
                ],
            },
            True,
        ),
        (
            {
                "type": "any",
                "conditions": [{"type": "never"}, {"type": "clue_discovered", "clue_id": "ghost"}],
            },
            False,
        ),
        ({"type": "not", "condition": {"type": "never"}}, True),
        ({"type": "not", "condition": {"type": "always"}}, False),
        (
            {
                "type": "count",
                "min": 2,
                "conditions": [
                    {"type": "always"},
                    {"type": "clue_discovered", "clue_id": "clue_key"},
                ],
            },
            True,
        ),
        (
            {
                "type": "count",
                "min": 3,
                "conditions": [
                    {"type": "always"},
                    {"type": "clue_discovered", "clue_id": "clue_key"},
                ],
            },
            False,
        ),
        ({"type": "always"}, True),
        ({"type": "never"}, False),
    )
