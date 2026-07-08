from __future__ import annotations

from copy import deepcopy

from typing_extensions import TypedDict

from engine.api.schemas.common import ActionType, JsonValue

RuntimeScalar = str | int | float | bool | None


class Message(TypedDict):
    id: str
    role: str
    character_id: str | None
    text: str
    emotion: str | None
    timestamp: str


class GameEvent(TypedDict):
    event_id: str
    actions: list[dict[str, JsonValue]]
    source: str


class EventActionRecord(TypedDict):
    event_id: str
    source: str
    action: str
    payload: dict[str, JsonValue]


class ClueDiscovery(TypedDict):
    clue_id: str
    round_id: str
    scene_id: str
    is_key: bool


class EvidencePresentation(TypedDict):
    evidence_id: str
    character_id: str


class PlayerActionRecord(TypedDict):
    action_id: str
    target: str | None


class CardUsageRecord(TypedDict):
    card_id: str
    card_type: str | None


class PlayerActionInput(TypedDict):
    action_id: ActionType
    target: str | None
    text: str | None


class BlockedTransition(TypedDict):
    from_stage: str
    to_stage: str
    reason: str


class GameState(TypedDict):
    session_id: str
    script_id: str
    player_id: str

    current_stage: str
    previous_stage: str | None
    next_stage: str | None
    completed_stages: list[str]
    completed_acts: list[str]
    stage_entered_at: str
    current_time: str
    stage_history: list[str]

    player_character_id: str
    npc_agents: dict[str, dict[str, RuntimeScalar]]
    npc_states: dict[str, dict[str, RuntimeScalar]]

    available_actions: list[str]
    available_characters: list[str]
    available_scenes: list[str]
    unlocked_scenes: list[str]
    current_scene: str
    unlocked_clues: list[str]
    discovered_clues: list[ClueDiscovery]
    discovered_evidences: list[str]
    evidences_shown_to_npcs: list[EvidencePresentation]
    completed_events: list[str]
    event_log: list[EventActionRecord]
    pending_media: list[dict[str, JsonValue]]

    chat_history: list[Message]
    pending_npc_responses: list[dict[str, JsonValue]]
    character_dialog_counts: dict[str, int]
    triggered_dialogs: list[str]
    player_utterances: list[str]

    performed_actions: list[PlayerActionRecord]
    player_requests: list[str]
    used_cards: list[CardUsageRecord]

    condition_cache: dict[str, bool]
    pending_events: list[GameEvent]
    pending_action: PlayerActionInput | None
    blocked_transitions: list[BlockedTransition]

    ending_triggered: bool
    ending_id: str | None
    final_submission: dict[str, JsonValue] | None
    answer_key: dict[str, JsonValue]
    deduction_chains_completed: list[str]
    session_counters: dict[str, int]
    is_first_play: bool
    hint_count: int


def create_initial_state(
    session_id: str,
    script_id: str,
    player_id: str,
    player_character_id: str,
    entry_stage: str = "prologue",
) -> GameState:
    return GameState(
        session_id=session_id,
        script_id=script_id,
        player_id=player_id,
        current_stage=entry_stage,
        previous_stage=None,
        next_stage=None,
        completed_stages=[],
        completed_acts=[],
        stage_entered_at="",
        current_time="",
        stage_history=[entry_stage],
        player_character_id=player_character_id,
        npc_agents={},
        npc_states={},
        available_actions=[],
        available_characters=[],
        available_scenes=[],
        unlocked_scenes=[],
        current_scene="",
        unlocked_clues=[],
        discovered_clues=[],
        discovered_evidences=[],
        evidences_shown_to_npcs=[],
        completed_events=[],
        event_log=[],
        pending_media=[],
        chat_history=[],
        pending_npc_responses=[],
        character_dialog_counts={},
        triggered_dialogs=[],
        player_utterances=[],
        performed_actions=[],
        player_requests=[],
        used_cards=[],
        condition_cache={},
        pending_events=[],
        pending_action=None,
        blocked_transitions=[],
        ending_triggered=False,
        ending_id=None,
        final_submission=None,
        answer_key={},
        deduction_chains_completed=[],
        session_counters={},
        is_first_play=True,
        hint_count=0,
    )


def clone_game_state(state: GameState) -> GameState:
    return deepcopy(state)
