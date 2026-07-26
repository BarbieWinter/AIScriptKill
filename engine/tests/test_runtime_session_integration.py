from datetime import UTC, datetime
from uuid import UUID

from engine.api.schemas import ActionRequest
from engine.core.game_state import GameState, clone_game_state, create_initial_state
from engine.repositories.session_models import SessionRuntimeState, StoredSession
from engine.services.runtime_action_mappers import runtime_action_input, runtime_action_result
from engine.services.runtime_state_mappers import (
    initial_game_state,
    project_runtime_state,
    synchronize_monotonic_progress,
)
from engine.tests.stategraph_fixtures import action_package


def _session(state: SessionRuntimeState | None = None) -> StoredSession:
    timestamp = datetime(2026, 7, 13, tzinfo=UTC)
    return StoredSession(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        script_id="minimal-case",
        player_id=None,
        player_character_id="player",
        state=state or SessionRuntimeState(current_stage="prologue"),
        status="in_progress",
        created_at=timestamp,
        updated_at=timestamp,
    )


def test_initial_game_state_preserves_rest_projection_without_using_it_as_continuation() -> None:
    session = _session(
        SessionRuntimeState(
            player_name="卓司元",
            current_stage="prologue",
            stage_name="序章",
            available_actions=["talk_to_npc"],
            available_characters=["npc"],
            discovered_evidences=["knife"],
            viewed_evidences=["knife"],
            unlocked_character_chapters=["chapter-1"],
            read_character_chapters=["chapter-1"],
            evidences_shown_to_npcs=[{"evidence_id": "knife", "character_id": "npc"}],
            current_scene="main_hall",
        )
    )

    state = initial_game_state(session)

    assert state["player_id"] == "anonymous"
    assert state["available_actions"] == ["talk_to_npc"]
    assert state["viewed_evidences"] == ["knife"]
    assert state["read_character_chapters"] == ["chapter-1"]
    assert state["evidences_shown_to_npcs"] == [{"evidence_id": "knife", "character_id": "npc"}]
    assert state["completed_events"] == []
    assert state["performed_actions"] == []


def test_monotonic_projection_progress_merges_into_restored_full_state() -> None:
    session = _session()
    restored = initial_game_state(session)
    restored["performed_actions"].append({"action_id": "open_clue_board", "target": None})
    projection = SessionRuntimeState(
        discovered_evidences=["knife"],
        viewed_evidences=["knife"],
        unlocked_character_chapters=["chapter-1"],
        read_character_chapters=["chapter-1"],
        evidences_shown_to_npcs=[{"evidence_id": "knife", "character_id": "npc"}],
    )

    merged = synchronize_monotonic_progress(restored, projection)

    assert merged["performed_actions"] == [{"action_id": "open_clue_board", "target": None}]
    assert merged["viewed_evidences"] == ["knife"]
    assert merged["read_character_chapters"] == ["chapter-1"]
    assert merged["evidences_shown_to_npcs"] == [{"evidence_id": "knife", "character_id": "npc"}]


def test_project_runtime_state_preserves_names_and_visible_graph_fields() -> None:
    session = _session(SessionRuntimeState(player_name="卓司元", stage_name="旧名称"))
    state = initial_game_state(session)
    state["current_stage"] = "act1"
    state["available_actions"] = ["open_clue_board"]
    state["pending_media"] = [{"id": "intro", "type": "bgm", "status": "queued"}]
    state["evidences_shown_to_npcs"] = [{"evidence_id": "knife", "character_id": "npc"}]

    projected = project_runtime_state(state, session.state, stage_name="第一幕")

    assert projected.player_name == "卓司元"
    assert projected.stage_name == "第一幕"
    assert projected.available_actions == ["open_clue_board"]
    assert projected.pending_media == [{"id": "intro", "type": "bgm", "status": "queued"}]
    assert projected.evidences_shown_to_npcs == [{"evidence_id": "knife", "character_id": "npc"}]


def test_rest_action_mapper_encodes_core_targets() -> None:
    assert (
        runtime_action_input(
            ActionRequest(action="talk_to_npc", character_id="npc", message="你见到了谁？")
        ).target
        == "npc"
    )
    assert (
        runtime_action_input(
            ActionRequest(action="examine_scene", scene_id="main_hall", hotspot_id="door")
        ).target
        == "main_hall:door"
    )
    assert (
        runtime_action_input(
            ActionRequest(action="show_evidence", evidence_id="knife", character_id="npc")
        ).target
        == "knife:npc"
    )
    assert (
        runtime_action_input(ActionRequest(action="request_advance", reason="玩家界面说明")).target
        == "request_advance"
    )
    assert runtime_action_input(ActionRequest(action="open_clue_board")).target is None


def test_runtime_action_result_returns_real_npc_message_delta() -> None:
    package = action_package()
    previous = create_initial_state(
        session_id="00000000-0000-0000-0000-000000000001",
        script_id=package.package.id,
        player_id="anonymous",
        player_character_id="player",
        entry_stage="prologue",
    )
    current = replace_game_state(previous)
    current["player_utterances"].append("你昨晚在哪里？")
    current["chat_history"].append(
        {
            "id": "npc-message-1",
            "role": "npc",
            "character_id": "npc",
            "text": "NPC 正在回应。",
            "emotion": None,
            "timestamp": "2026-07-13T00:00:00Z",
        }
    )

    response, effect = runtime_action_result(
        ActionRequest(action="talk_to_npc", character_id="npc", message="你昨晚在哪里？"),
        previous,
        current,
        package,
    )

    assert response.type == "npc_response"
    assert response.text == "NPC 正在回应。"
    assert [(item.role, item.text, item.message_id) for item in effect.chat_messages] == [
        ("player", "你昨晚在哪里？", None),
        ("npc", "NPC 正在回应。", "npc-message-1"),
    ]


def replace_game_state(state: GameState) -> GameState:
    return clone_game_state(state)
