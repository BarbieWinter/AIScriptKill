from engine.core.game_state import GameState, create_initial_state
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import ScriptPackageImport
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


class ManualClock:
    def __init__(self, timestamp: str) -> None:
        self._timestamp = timestamp

    def now(self) -> str:
        return self._timestamp

    def set(self, timestamp: str) -> None:
        self._timestamp = timestamp


def action_package() -> ScriptPackageImport:
    files = minimal_package_files()
    files["stages/prologue.yml"] = """
id: "prologue"
name: "序章"
sort_order: 0
entry_conditions: []
exit_conditions:
  - type: "never"
available_actions:
  - talk_to_npc
  - examine_scene
  - show_evidence
  - use_card
  - open_clue_board
  - request_advance
available_characters:
  - player
  - npc
available_scenes:
  - main_hall
on_stage_entry:
  - action: "dm_narrate"
    text: "序章开始"
"""
    files["evidences/knife.yml"] = """
id: "knife"
name: "刀"
description:
  surface: "一把刀"
discovery:
  scene_id: "main_hall"
  hotspot_id: "back_door"
"""
    files["scenes/main_hall.yml"] = """
id: "main_hall"
name: "大厅"
visual:
  background: "assets/scenes/main_hall.jpg"
available_in_stages:
  - prologue
  - act1
  - review
hotspots:
  - id: "back_door"
    on_click:
      - action: "clue_discover"
        clue_id: "clue_1"
      - action: "evidence_discover"
        evidence_id: "knife"
      - action: "dm_narrate"
        text: "你在后门旁发现了一把刀。"
"""
    return load_package_archive(package_archive(files))


def initial_state(package: ScriptPackageImport) -> GameState:
    return create_initial_state(
        session_id="00000000-0000-0000-0000-000000000001",
        script_id=package.package.id,
        player_id="00000000-0000-0000-0000-000000000002",
        player_character_id="player",
        entry_stage="prologue",
    )


def elapsed_time_package() -> ScriptPackageImport:
    files = minimal_package_files()
    files["stages/prologue.yml"] = """
id: "prologue"
name: "序章"
sort_order: 0
entry_conditions: []
exit_conditions:
  - type: "time_elapsed"
    minutes: 5
    since_stage_entry: true
available_actions:
  - open_clue_board
available_characters:
  - player
available_scenes:
  - main_hall
"""
    files["stages/act1.yml"] = """
id: "act1"
name: "第一幕"
sort_order: 10
entry_conditions: []
exit_conditions:
  - type: "never"
available_actions:
  - open_clue_board
available_characters:
  - player
available_scenes:
  - main_hall
"""
    return load_package_archive(package_archive(files))


def composite_event_package() -> ScriptPackageImport:
    files = minimal_package_files()
    files["stages/prologue.yml"] = """
id: "prologue"
name: "序章"
sort_order: 0
entry_conditions: []
exit_conditions:
  - type: "never"
available_actions:
  - open_clue_board
available_characters:
  - player
  - npc
available_scenes:
  - main_hall
on_clue_discovered:
  - condition:
      type: "all"
      conditions:
        - type: "clue_discovered"
          clue_id: "clue_1"
        - type: "any"
          conditions:
            - type: "character_talked_to"
              character_id: "npc"
              min_count: 2
            - type: "evidence_found"
              evidence_id: "knife"
    then:
      - action: "dm_narrate"
        text: "复合条件命中"
"""
    files["evidences/knife.yml"] = """
id: "knife"
name: "刀"
description:
  surface: "一把刀"
discovery:
  scene_id: "main_hall"
"""
    return load_package_archive(package_archive(files))


def state_graph_package_files() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = dict(minimal_package_files())
    files["stages/prologue.yml"] = """
id: "prologue"
name: "序章"
sort_order: 0
entry_conditions: []
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
entry_conditions: []
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


def state_graph_package() -> ScriptPackageImport:
    return load_package_archive(package_archive(state_graph_package_files()))
