from __future__ import annotations

from typing_extensions import TypedDict

from engine.api.schemas.common import JsonValue

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


class GameState(TypedDict):
    session_id: str
    script_id: str
    player_id: str

    current_stage: str
    previous_stage: str | None
    completed_stages: list[str]
    completed_acts: list[str]
    stage_entered_at: str
    current_time: str

    player_character_id: str
    npc_states: dict[str, dict[str, RuntimeScalar]]

    unlocked_clues: list[str]
    discovered_clues: list[ClueDiscovery]
    discovered_evidences: list[str]
    evidences_shown_to_npcs: list[EvidencePresentation]
    completed_events: list[str]

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
        completed_stages=[],
        completed_acts=[],
        stage_entered_at="",
        current_time="",
        player_character_id=player_character_id,
        npc_states={},
        unlocked_clues=[],
        discovered_clues=[],
        discovered_evidences=[],
        evidences_shown_to_npcs=[],
        completed_events=[],
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
        ending_triggered=False,
        ending_id=None,
        final_submission=None,
        answer_key={},
        deduction_chains_completed=[],
        session_counters={},
        is_first_play=True,
        hint_count=0,
    )
