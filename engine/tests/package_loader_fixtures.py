from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from typing import TypeAlias
from zipfile import ZipFile

PackageFileContent: TypeAlias = str | bytes


def package_archive(files: Mapping[str, PackageFileContent]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def write_package_directory(package_dir: Path, files: Mapping[str, PackageFileContent]) -> None:
    for path, content in files.items():
        target = package_dir / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")


def minimal_package_files() -> dict[str, str]:
    return {
        "package.yml": """
metadata:
  id: "minimal-case"
  title: "最小测试剧本"
  version: "1.0.0"
info:
  description: "用于 T-2.1 验收的最小剧本包"
  genre: ["test"]
  difficulty: 2
  duration_minutes: 60
  max_players: 1
engine:
  entry_stage: "prologue"
  default_ending: "truth"
""",
        "stages/_index.yml": """
stages:
  - id: "prologue"
    name: "序章"
    sort_order: 0
  - id: "act1"
    name: "第一幕"
    sort_order: 10
  - id: "review"
    name: "复盘"
    sort_order: 20
acts:
  - id: "book1"
    name: "第一本"
    stages: ["prologue", "act1"]
  - id: "review_act"
    name: "复盘"
    stages: ["review"]
""",
        "stages/prologue.yml": """
id: "prologue"
name: "序章"
sort_order: 0
available_actions:
  - talk_to_npc
available_characters:
  - player
  - npc
available_scenes:
  - main_hall
""",
        "stages/act1.yml": """
id: "act1"
name: "第一幕"
sort_order: 10
available_actions:
  - examine_scene
available_characters:
  - player
available_scenes:
  - main_hall
""",
        "stages/review.yml": """
id: "review"
name: "复盘"
sort_order: 20
available_actions:
  - open_clue_board
available_characters:
  - player
available_scenes:
  - main_hall
""",
        "characters/_index.yml": """
characters:
  - id: "player"
    name: "玩家角色"
    playable: true
    order: 1
  - id: "npc"
    name: "NPC角色"
    playable: false
    order: 2
""",
        "characters/player.yml": """
id: "player"
name: "玩家角色"
identity:
  public: "调查者"
personality:
  summary: "冷静"
knowledge:
  prologue:
    knows:
      - "自己来到现场"
  act1:
    knows:
      - "发现大厅线索"
  review:
    knows:
      - "进入复盘"
""",
        "characters/npc.yml": """
id: "npc"
name: "NPC角色"
identity:
  public: "目击者"
personality:
  summary: "紧张"
knowledge:
  prologue:
    knows:
      - "见过可疑的人"
  act1:
    knows:
      - "知道部分现场信息"
  review:
    knows:
      - "等待复盘"
""",
        "scenes/main_hall.yml": """
id: "main_hall"
name: "大厅"
available_in_stages:
  - prologue
  - act1
  - review
""",
        "clues/rounds/act1_round1.yml": """
round_id: "act1_round1"
name: "第一轮搜证"
stage_visible: "act1"
clues:
  - id: "clue_1"
    name: "线索一"
    description: "第一条线索"
    related_scene: "main_hall"
    related_characters: ["player"]
  - id: "clue_2"
    name: "线索二"
    description: "第二条线索"
    related_scene: "main_hall"
    related_characters: ["npc"]
  - id: "clue_3"
    name: "线索三"
    description: "第三条线索"
    related_scene: "main_hall"
  - id: "clue_4"
    name: "线索四"
    description: "第四条线索"
    related_scene: "main_hall"
""",
        "endings.yml": """
endings:
  - id: "truth"
    name: "真相复盘"
    condition:
      type: "submission_correct"
      field: "suspect"
      value: "npc"
    on_trigger:
      - action: "transition_to"
        stage_id: "review"
    outcome_text: "真相已经揭开。"
""",
    }
