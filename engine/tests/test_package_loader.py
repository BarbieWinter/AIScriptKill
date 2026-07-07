from pathlib import Path

import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive, load_package_directory
from engine.tests.package_loader_fixtures import (
    minimal_package_files,
    package_archive,
    write_package_directory,
)


def test_load_package_archive_accepts_minimal_package_when_references_are_valid() -> None:
    # Given: a valid package with the T-2.1 minimum structure.
    archive = package_archive(minimal_package_files())

    # When: the package is parsed for publication.
    package = load_package_archive(archive, publish=True)

    # Then: all required package sections are normalized into import records.
    assert package.package.id == "minimal-case"
    assert package.package.status == "published"
    assert len(package.stages) == 3
    assert [stage.id for stage in package.stages] == ["prologue", "act1", "review"]
    assert package.stages[0].definition["act_id"] == "book1"
    assert len(package.characters) == 2
    assert len(package.clues) == 4
    assert package.clues[0].metadata["related_scene"] == "main_hall"


def test_load_package_directory_accepts_loose_package_when_references_are_valid(
    tmp_path: Path,
) -> None:
    # Given: the same valid package exists as a loose script-packages/<id>/ directory.
    package_dir = tmp_path / "minimal-case"
    write_package_directory(package_dir, minimal_package_files())

    # When: the package directory is parsed directly.
    package = load_package_directory(package_dir, publish=True)

    # Then: it produces the same import records as the zip archive path.
    assert package.package.id == "minimal-case"
    assert package.package.status == "published"
    assert len(package.stages) == 3
    assert len(package.characters) == 2


def test_load_package_archive_rejects_missing_entry_stage_when_manifest_points_elsewhere() -> None:
    # Given: package.yml references an entry stage that has no stage YAML.
    files = minimal_package_files()
    files["package.yml"] = files["package.yml"].replace(
        'entry_stage: "prologue"',
        'entry_stage: "missing_stage"',
    )

    # When / Then: validation reports the invalid manifest-to-stage reference.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "engine.entry_stage" in exc_info.value.message
    assert "missing_stage" in exc_info.value.message


def test_load_package_archive_rejects_stage_with_unknown_character_reference() -> None:
    # Given: a stage references a character that is not defined in characters/.
    files = minimal_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "- npc",
        "- ghost",
    )

    # When / Then: validation rejects the unknown stage character reference.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "prologue" in exc_info.value.message
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_stage_with_unknown_clue_round_reference() -> None:
    # Given: a stage references a clue round that does not exist in clues/rounds/.
    files = minimal_package_files()
    files["stages/prologue.yml"] = (
        f"{files['stages/prologue.yml']}\navailable_clue_rounds:\n  - missing_round\n"
    )

    # When / Then: validation rejects the unknown clue round reference.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "prologue" in exc_info.value.message
    assert "missing_round" in exc_info.value.message


def test_load_package_archive_rejects_duplicate_clue_ids() -> None:
    # Given: two clue records resolve to the same package-level clue ID.
    files = minimal_package_files()
    files["clues/rounds/act1_round1.yml"] = files["clues/rounds/act1_round1.yml"].replace(
        'id: "clue_4"',
        'id: "clue_1"',
    )

    # When / Then: validation rejects the duplicate ID before import.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_DUPLICATE_ID"
    assert "clue" in exc_info.value.message
    assert "clue_1" in exc_info.value.message


def test_load_package_archive_normalizes_documented_action_objects() -> None:
    # Given: a stage uses SCRIPT_PACKAGE_SCHEMA.md action objects instead of strings.
    files = minimal_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "  - talk_to_npc",
        '  - id: "talk_to_npc"\n    label: "对话角色"\n    description: "与 NPC 对话"',
    )

    # When: the package is loaded.
    package = load_package_archive(package_archive(files))

    # Then: runtime-facing stage definitions keep string action IDs.
    prologue = next(stage for stage in package.stages if stage.id == "prologue")
    assert prologue.definition["available_actions"] == ["talk_to_npc"]
    assert prologue.definition["action_definitions"] == [
        {"id": "talk_to_npc", "label": "对话角色", "description": "与 NPC 对话"},
    ]


def test_load_package_archive_rejects_unknown_stage_event_action() -> None:
    # Given: a stage entry event names an action the engine does not support.
    files = minimal_package_files()
    files["stages/prologue.yml"] = (
        f'{files["stages/prologue.yml"]}\non_stage_entry:\n  - action: "rewrite_murderer"\n'
    )

    # When / Then: validation rejects the unsupported event action name.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_EVENT_ACTION_INVALID"
    assert "rewrite_murderer" in exc_info.value.message


def test_load_package_archive_rejects_evidence_reaction_with_unknown_character() -> None:
    # Given: an evidence NPC reaction points at a missing character.
    files = minimal_package_files()
    files["evidences/knife.yml"] = """
id: "knife"
name: "刀"
description:
  surface: "一把刀"
discovery:
  scene_id: "main_hall"
npc_reactions:
  - character_id: "ghost"
    text: "不存在的角色"
"""

    # When / Then: validation rejects the unknown character reference.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_missing_local_asset_file() -> None:
    # Given: a clue references a local asset path that is not present in the package.
    files = minimal_package_files()
    files["clues/rounds/act1_round1.yml"] = files["clues/rounds/act1_round1.yml"].replace(
        'name: "线索一"',
        'name: "线索一"\n    image: "assets/clues/missing.jpg"',
    )

    # When / Then: validation reports the missing package asset.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_ASSET_MISSING"
    assert "assets/clues/missing.jpg" in exc_info.value.message


def test_load_package_archive_warns_when_character_lacks_stage_knowledge() -> None:
    # Given: one character only defines knowledge for the entry stage.
    files = minimal_package_files()
    files["characters/npc.yml"] = """
id: "npc"
name: "NPC角色"
personality:
  summary: "紧张"
knowledge:
  prologue:
    knows:
      - "见过可疑的人"
"""

    # When: the package is loaded successfully.
    package = load_package_archive(package_archive(files))

    # Then: validation keeps the package importable but reports knowledge coverage gaps.
    assert package.warnings == ("character npc 缺少阶段知识: act1, review",)
