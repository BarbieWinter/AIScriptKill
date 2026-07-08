from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy.sql import ClauseElement

from engine.api.schemas.common import JsonValue
from engine.core.checkpoint import SupabaseSessionCheckpointSaver
from engine.core.game_state import create_initial_state
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import JsonMapping
from engine.core.script_engine import ScriptEngine
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive

type CheckpointRow = dict[str, str | dict[str, JsonValue] | None]


async def test_script_engine_runs_stage_transition_and_ending_with_event_sequence() -> None:
    # Given: a package whose prologue entry event unlocks content and whose player action exits.
    package = load_package_archive(package_archive(_state_graph_package_files()))
    event_sink = RecordingEventSink()
    engine = ScriptEngine.from_package(package, event_sink=event_sink)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # When: the player asks the DM to advance out of the prologue.
    state = await engine.run_action(state, action_id="request_advance", target="request_advance")

    # Then: the graph performs entry events, action processing, condition checking and stage entry.
    assert state["current_stage"] == "act1"
    assert state["previous_stage"] == "prologue"
    assert "prologue" in state["completed_stages"]
    assert "clue_1" in state["unlocked_clues"]
    assert event_sink.actions == [
        "dm_narrate",
        "play_audio",
        "unlock_clue_round",
        "play_audio",
        "save_checkpoint",
        "dm_narrate",
    ]

    # When: the player supplies a correct final submission in act1.
    state["final_submission"] = {
        "suspect": "npc",
        "key_evidences": ["knife"],
    }
    state["answer_key"] = {"suspect": "npc"}
    state = await engine.run_action(state, action_id="request_advance", target="finish")

    # Then: ending conditions fire and ending actions run exactly once.
    assert state["ending_triggered"] is True
    assert state["ending_id"] == "truth"
    assert event_sink.actions[-2:] == ["dm_narrate", "play_audio"]


async def test_script_engine_restores_state_from_langgraph_checkpoint() -> None:
    # Given: a compiled graph with a LangGraph checkpointer and one completed action.
    package = load_package_archive(package_archive(_state_graph_package_files()))
    checkpointer = InMemorySaver()
    session_id = str(uuid4())
    engine = ScriptEngine.from_package(package, checkpointer=checkpointer)
    state = create_initial_state(
        session_id=session_id,
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )
    await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
        thread_id=session_id,
    )

    # When: a new engine instance is created with the same checkpointer after a process restart.
    restarted_engine = ScriptEngine.from_package(package, checkpointer=checkpointer)
    restored_state = await restarted_engine.restore_state(thread_id=session_id)

    # Then: the latest checkpoint rebuilds the full GameState.
    assert restored_state is not None
    assert restored_state["current_stage"] == "act1"
    assert restored_state["previous_stage"] == "prologue"
    assert restored_state["unlocked_clues"] == ["clue_1", "clue_2", "clue_3", "clue_4"]


async def test_script_engine_restores_state_from_session_checkpoints_after_restart() -> None:
    # Given: a Supabase-backed saver that persists LangGraph checkpoints into session_checkpoints.
    package = load_package_archive(package_archive(_state_graph_package_files()))
    session = RecordingCheckpointSession()
    session_id = str(uuid4())
    engine = ScriptEngine.from_package(
        package,
        checkpointer=SupabaseSessionCheckpointSaver(session),
    )
    state = create_initial_state(
        session_id=session_id,
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )
    await engine.run_action(
        state,
        action_id="request_advance",
        target="request_advance",
        thread_id=session_id,
    )

    # When: a new engine uses the same checkpoint table after the original process is gone.
    restarted_engine = ScriptEngine.from_package(
        package,
        checkpointer=SupabaseSessionCheckpointSaver(session),
    )
    restored_state = await restarted_engine.restore_state(thread_id=session_id)

    # Then: the persisted session checkpoint is enough to continue from the advanced stage.
    assert restored_state is not None
    assert restored_state["current_stage"] == "act1"
    assert restored_state["previous_stage"] == "prologue"
    assert len(session.rows) > 0


async def test_script_engine_rejects_stage_jump_without_stage_permission() -> None:
    # Given: a stage entry event tries to jump from prologue directly to review.
    files = _state_graph_package_files()
    prologue_file = files["stages/prologue.yml"]
    if not isinstance(prologue_file, str):
        raise AssertionError("prologue stage fixture must be text")
    transition_event = "\n".join(
        [
            '  - action: "play_audio"',
            '    asset_id: "intro"',
            '  - action: "transition_to"',
            '    stage_id: "review"',
        ],
    )
    files["stages/prologue.yml"] = prologue_file.replace(
        '  - action: "play_audio"\n    asset_id: "intro"',
        transition_event,
    )
    package = load_package_archive(package_archive(files))
    engine = ScriptEngine.from_package(package)
    state = create_initial_state(
        session_id=str(uuid4()),
        script_id=package.package.id,
        player_id=str(uuid4()),
        player_character_id="player",
        entry_stage="prologue",
    )

    # When: the graph executes prologue entry and the player action.
    state = await engine.run_action(state, action_id="open_clue_board")

    # Then: the illegal jump is recorded but the stage does not skip ahead.
    assert state["current_stage"] == "prologue"
    assert state["blocked_transitions"] == [
        {"from_stage": "prologue", "to_stage": "review", "reason": "stage_jump_denied"},
    ]


class RecordingEventSink:
    def __init__(self) -> None:
        self.actions: list[str] = []

    async def execute(self, action: str, payload: JsonMapping) -> None:
        _ = payload
        self.actions.append(action)


class RecordingCheckpointSession:
    def __init__(self) -> None:
        self.rows: list[CheckpointRow] = []

    async def execute(self, statement: ClauseElement) -> "RecordingCheckpointResult":
        table_name = getattr(getattr(statement, "table", None), "name", None)
        if table_name == "session_checkpoints":
            params = statement.compile().params
            thread_ts = params.get("thread_ts") if isinstance(params, dict) else None
            state = params.get("state") if isinstance(params, dict) else None
            if not isinstance(thread_ts, str) or not isinstance(state, dict):
                return RecordingCheckpointResult(self.rows)
            self.rows.append(
                {
                    "thread_ts": thread_ts,
                    "parent_ts": params.get("parent_ts") if isinstance(params, dict) else None,
                    "state": state,
                },
            )
        return RecordingCheckpointResult(self.rows)


class RecordingCheckpointResult:
    def __init__(self, rows: list[CheckpointRow]) -> None:
        self._rows = rows

    def mappings(self) -> "RecordingCheckpointResult":
        return self

    def one_or_none(self) -> CheckpointRow | None:
        if len(self._rows) == 0:
            return None
        return self._rows[-1]

    def all(self) -> list[CheckpointRow]:
        return list(reversed(self._rows))


def _state_graph_package_files() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = dict(minimal_package_files())
    files["stages/prologue.yml"] = """
id: "prologue"
name: "序章"
sort_order: 0
available_actions:
  - request_advance
  - open_clue_board
available_characters:
  - player
  - npc
available_scenes:
  - main_hall
available_clue_rounds:
  - act1_round1
exit_conditions:
  - type: "player_requested"
    dialog_id: "request_advance"
on_stage_entry:
  - action: "dm_narrate"
    text: "序章开始"
  - action: "play_audio"
    asset_id: "intro"
  - action: "unlock_clue_round"
    round_id: "act1_round1"
on_stage_exit:
  - action: "save_checkpoint"
media_triggers:
  - event: "clue_discovered"
    clue_id: "clue_1"
    then:
      - action: "play_audio"
        asset_id: "intro"
"""
    files["stages/act1.yml"] = """
id: "act1"
name: "第一幕"
sort_order: 10
available_actions:
  - request_advance
available_characters:
  - player
available_scenes:
  - main_hall
exit_conditions:
  - type: "submission_correct"
    field: "suspect"
    value: "npc"
on_stage_entry:
  - action: "dm_narrate"
    text: "第一幕开始"
"""
    files["media/default.yml"] = """
audio_assets:
  - id: "intro"
    type: "bgm"
    file: "assets/audio/intro.mp3"
  - id: "ending_audio"
    type: "story"
    file: "assets/audio/ending.mp3"
"""
    files["evidences/knife.yml"] = """
id: "knife"
name: "刀"
description:
  surface: "一把刀"
discovery:
  scene_id: "main_hall"
"""
    files["endings.yml"] = """
endings:
  - id: "truth"
    name: "真相复盘"
    condition:
      type: "submission_correct"
      field: "suspect"
      value: "npc"
    on_trigger:
      - action: "dm_narrate"
        text: "真相揭开"
      - action: "play_audio"
        asset_id: "ending_audio"
"""
    files["assets/audio/intro.mp3"] = b"intro"
    files["assets/audio/ending.mp3"] = b"ending"
    return files
