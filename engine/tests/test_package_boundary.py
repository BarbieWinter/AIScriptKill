import os
import stat
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

import engine.core.package_archive as package_archive_module
import engine.core.package_reference_validation as package_reference_validation_module
from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive, load_package_directory
from engine.core.package_schema import JsonMapping
from engine.core.package_validation_context import PackageValidationContext
from engine.tests.package_loader_fixtures import (
    minimal_package_files,
    package_archive,
    write_package_directory,
)


def valid_character_chapter() -> str:
    return """---
chapter_id: chapter-01
character_id: player
order: 1
title: 第一章
visibility: character_only
release:
  type: game_start
stage_min: prologue
---

章节正文。
"""


def test_load_package_archive_rejects_missing_stage_entry_conditions() -> None:
    # 给定：某个阶段缺少已发布剧本包 schema 要求的字段。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "entry_conditions: []\n",
        "",
    )

    # 当/则：剧本包边界拒绝不完整的阶段。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "entry_conditions" in exc_info.value.message


def test_load_package_archive_rejects_missing_stage_exit_conditions() -> None:
    # 给定：某个阶段缺少已发布剧本包 schema 要求的字段。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []\n",
        "",
    )

    # 当/则：剧本包边界拒绝不完整的阶段。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "exit_conditions" in exc_info.value.message


def test_load_package_archive_rejects_missing_stage_available_actions() -> None:
    # 给定：某个阶段缺少已发布剧本包 schema 要求的字段。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "available_actions:\n  - talk_to_npc\n",
        "",
    )

    # 当/则：剧本包边界拒绝不完整的阶段。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "available_actions" in exc_info.value.message


def test_load_package_archive_requires_character_index() -> None:
    # 给定：存在角色 YAML 文件，但缺少必需的 characters/_index.yml。
    files = _strict_package_files()
    del files["characters/_index.yml"]

    # 当/则：加载器拒绝定义不明确的角色目录。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_INDEX_REQUIRED"


def test_load_package_archive_requires_character_files_to_match_index() -> None:
    # 给定：索引声明了一个没有对应 YAML 定义的角色。
    files = _strict_package_files()
    files["characters/_index.yml"] += "\n  - id: missing\n    name: Missing\n"

    # 当/则：记录进入数据库前，索引与文件的一致性校验失败。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_INDEX_INVALID"


def test_load_package_archive_rejects_stage_act_conflict() -> None:
    # 给定：阶段文件与 stages/_index.yml 中的幕归属冲突。
    files = _strict_package_files()
    files["stages/prologue.yml"] += "act_id: review_act\n"

    # 当/则：索引仍是幕归属关系的唯一权威来源。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_STAGE_ACT_CONFLICT"


def test_load_package_archive_rejects_unknown_act_condition_reference() -> None:
    # 给定：条件引用了 stages/_index.yml 中不存在的幕。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        "exit_conditions:\n  - type: act_completed\n    act_id: missing",
    )

    # 当/则：幕引用与阶段、内容引用一并校验。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"


def test_load_package_archive_rejects_event_payload_with_scalar_scene_ids() -> None:
    # 给定：unlock_scenes 使用标量，运行时原本会将其视为空列表。
    files = _strict_package_files()
    files["stages/prologue.yml"] += (
        "on_stage_entry:\n  - action: unlock_scenes\n    scene_ids: main_hall\n"
    )

    # 当/则：动作专用载荷校验拒绝这种无提示的空操作。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_EVENT_PAYLOAD_INVALID"


def test_load_package_archive_rejects_evidence_type_outside_database_enum() -> None:
    # 给定：某种证物类型通过校验后会违反数据库 CHECK 约束。
    files = _strict_package_files()
    files["evidences/invalid.yml"] = """
id: invalid
name: Invalid
type: unsupported
description:
  surface: invalid
discovery:
  scene_id: main_hall
"""

    # 当/则：严格 YAML 模型在执行 SQL 前将其拒绝。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"


def test_load_package_archive_rejects_clue_without_own_stage_visible() -> None:
    # 给定：线索依赖所属轮次的阶段，而未声明自身的必填字段。
    files = _strict_package_files()
    files["clues/rounds/act1_round1.yml"] = files["clues/rounds/act1_round1.yml"].replace(
        '    stage_visible: "act1"\n', "", 1
    )

    # 当/则：强制执行线索级 schema 要求。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "stage_visible" in exc_info.value.message


def test_load_package_archive_rejects_unknown_clue_round_stage() -> None:
    # 给定：线索自身阶段合法，但所属轮次引用了不存在的阶段。
    files = _strict_package_files()
    files["clues/rounds/act1_round1.yml"] = files["clues/rounds/act1_round1.yml"].replace(
        'stage_visible: "act1"', 'stage_visible: "ghost"', 1
    )

    # 当/则：轮次阶段不会在展开线索记录时丢失，而是在统一引用边界被拒绝。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "clue round act1_round1" in exc_info.value.message
    assert "ghost" in exc_info.value.message


@pytest.mark.parametrize("unknown_stage_key", ("ghost", "stage_ghost"))
def test_load_package_archive_rejects_unknown_character_knowledge_stage(
    unknown_stage_key: str,
) -> None:
    # 给定：角色知识映射包含直接或兼容前缀形式的未知阶段。
    files = _strict_package_files()
    files["characters/player.yml"] = files["characters/player.yml"].replace(
        "knowledge:\n",
        f'knowledge:\n  {unknown_stage_key}:\n    knows: ["未来信息"]\n',
        1,
    )

    # 当/则：未知知识阶段是悬空引用，不再被误报为普通覆盖 warning。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "知识阶段引用" in exc_info.value.message
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_non_object_condition_child() -> None:
    # 给定：逻辑条件包含无法求值的标量子项。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: all
    conditions:
      - type: always
      - malformed
""".rstrip(),
    )

    # 当/则：拒绝格式错误的子项，而不是静默丢弃。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"


def test_load_package_archive_rejects_misspelled_condition_parameter() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: player_said_keyword
    keyword: clue
    case_sensitiv: false""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"
    assert "stage prologue exit_conditions" in exc_info.value.message
    assert "case_sensitiv" in exc_info.value.message


def test_load_package_archive_validates_short_circuited_condition_leaf() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: all
    conditions:
      - type: never
      - type: time_elapsed
        minutes: '20'""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"
    assert "time_elapsed.minutes" in exc_info.value.message


@pytest.mark.parametrize("timestamp", ["tomorrow", "2026-07-11T12:00:00"])
def test_load_package_archive_rejects_invalid_or_naive_real_time(timestamp: str) -> None:
    # 给定：阶段条件包含非 ISO 格式或不带时区的墙上时钟值。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        f'exit_conditions:\n  - type: real_time_reached\n    time: "{timestamp}"',
    )

    # 当/则：剧本包导入在玩法逻辑比较日期时间前将其拒绝。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"
    assert "ISO" in exc_info.value.message


def test_load_package_archive_rejects_negative_condition_threshold() -> None:
    # 给定：某个时间条件原本会立即为真。
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        "exit_conditions:\n  - type: time_elapsed\n    minutes: -1",
    )

    # 当/则：在剧本包边界校验数值阈值。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"
    assert "非负整数" in exc_info.value.message


def test_load_package_archive_rejects_condition_structure_key_on_leaf() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: always
    conditions: []""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_INVALID"
    assert "always" in exc_info.value.message


def test_load_package_archive_preserves_unknown_top_level_condition_type_error() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: future_condition""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_TYPE_INVALID"


def test_load_package_archive_maps_unknown_nested_condition_type_error() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: all
    conditions:
      - type: future_condition""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CONDITION_TYPE_INVALID"


def test_load_package_archive_validates_reference_in_nested_known_condition() -> None:
    files = _strict_package_files()
    files["stages/prologue.yml"] = files["stages/prologue.yml"].replace(
        "exit_conditions: []",
        """exit_conditions:
  - type: all
    conditions:
      - type: stage_completed
        stage_id: ghost""",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


def test_validate_condition_parses_deep_tree_once(monkeypatch: pytest.MonkeyPatch) -> None:
    condition: JsonMapping = {
        "type": "all",
        "conditions": [
            {
                "type": "any",
                "conditions": [
                    {
                        "type": "not",
                        "condition": {
                            "type": "count",
                            "min": 1,
                            "conditions": [{"type": "always"}, {"type": "never"}],
                        },
                    }
                ],
            }
        ],
    }
    context = PackageValidationContext(
        stage_ids=frozenset(),
        act_ids=frozenset(),
        character_ids=frozenset(),
        chapter_ids=frozenset(),
        clue_ids=frozenset(),
        evidence_ids=frozenset(),
        scene_ids=frozenset(),
        media_ids=frozenset(),
        clue_round_ids=frozenset(),
        ending_ids=frozenset(),
        available_files=frozenset(),
    )
    parse_calls = 0
    real_parse_condition = package_reference_validation_module.parse_condition

    def counting_parse_condition(raw_condition: JsonMapping):
        nonlocal parse_calls
        parse_calls += 1
        return real_parse_condition(raw_condition)

    monkeypatch.setattr(
        package_reference_validation_module,
        "parse_condition",
        counting_parse_condition,
    )

    package_reference_validation_module.validate_condition("deep condition", condition, context)

    assert parse_calls == 1


def test_load_package_archive_rejects_unknown_stage_field() -> None:
    # 给定：阶段包含已记录或已导入契约之外的字段。
    files = _strict_package_files()
    files["stages/prologue.yml"] += "unsupported_magic: true\n"

    # 当/则：未知输入不会被静默保留在运行时状态中。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "unsupported_magic" in exc_info.value.message


def test_load_package_archive_rejects_string_manifest_integer() -> None:
    # 给定：清单中的整数以可强制转换的 YAML 字符串提供。
    files = _strict_package_files()
    files["package.yml"] = files["package.yml"].replace("difficulty: 2", 'difficulty: "2"')

    # 当/则：严格剧本包模型拒绝错误的标量类型。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "difficulty" in exc_info.value.message


def test_load_package_archive_rejects_string_stage_index_integer() -> None:
    # 给定：阶段索引中的整数以可强制转换的 YAML 字符串提供。
    files = _strict_package_files()
    files["stages/_index.yml"] = files["stages/_index.yml"].replace(
        "sort_order: 0",
        'sort_order: "0"',
        1,
    )

    # 当/则：严格的阶段索引边界拒绝强制转换。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "sort_order" in exc_info.value.message


def test_load_package_archive_rejects_reserved_personal_clue_format() -> None:
    # 给定：剧本包在 T-4.2 schema 就绪前使用了保留目录。
    files = _strict_package_files()
    files["clues/personal/player.yml"] = 'character_id: "player"\nclues: []\n'

    # 当/则：导入器拒绝该内容，而不是将其静默丢弃。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_PERSONAL_CLUES_UNSUPPORTED"


def test_load_package_archive_rejects_scalar_clue_trigger() -> None:
    # 给定：on_clue_discovered 包含标量而非触发器对象。
    files = _strict_package_files()
    files["stages/prologue.yml"] += "on_clue_discovered:\n  - malformed\n"

    # 当/则：剧本包导入期间拒绝格式错误的触发器。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MAPPING_LIST_INVALID"


def test_load_package_archive_rejects_scalar_clue_trigger_condition() -> None:
    # 给定：线索触发器的条件载荷是标量。
    files = _strict_package_files()
    files["stages/prologue.yml"] += """
on_clue_discovered:
  - condition: malformed
    then: []
"""

    # 当/则：运行时求值前，条件必须是对象。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"


def test_load_package_archive_rejects_scalar_clue_trigger_action() -> None:
    # 给定：线索触发器的 then 列表包含标量动作。
    files = _strict_package_files()
    files["stages/prologue.yml"] += """
on_clue_discovered:
  - condition:
      type: always
    then:
      - malformed
"""

    # 当/则：事件总线消费动作列表前将其拒绝。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MAPPING_LIST_INVALID"


def test_load_package_archive_validates_clue_trigger_action_reference() -> None:
    # 给定：线索触发器动作指向剧本包中不存在的线索。
    files = _strict_package_files()
    files["stages/prologue.yml"] += """
on_clue_discovered:
  - condition:
      type: always
    then:
      - action: clue_discover
        clue_id: ghost
"""

    # 当/则：共享事件校验器拒绝缺失的引用。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


@pytest.mark.parametrize(
    ("trigger", "expected_code"),
    [
        (
            "  - event: unsupported\n    clue_id: clue_1\n"
            "    then:\n      - action: play_audio\n        asset_id: intro\n",
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            "  - event: clue_discovered\n    clue_id: clue_1\n",
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            "  - event: clue_discovered\n    clue_id: ghost\n"
            "    then:\n      - action: play_audio\n        asset_id: intro\n",
            "PACKAGE_REFERENCE_INVALID",
        ),
    ],
    ids=("unsupported-event", "missing-actions", "unknown-clue"),
)
def test_load_package_archive_rejects_invalid_media_trigger_envelope(
    trigger: str,
    expected_code: str,
) -> None:
    # 给定：媒体触发器原本会成为运行时不可观察的空操作。
    files = _strict_package_files()
    files["stages/prologue.yml"] += "media_triggers:\n" + trigger

    # 当/则：其信封和引用无法通过剧本包边界校验。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == expected_code


def test_load_package_archive_rejects_unsafe_member_path() -> None:
    # 给定：其他方面有效的归档包含越出剧本包根目录的路径。
    files = _strict_package_files()
    files["../escape.txt"] = "outside"

    # 当/则：消费剧本包成员前先检查路径安全性。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_ARCHIVE_PATH_UNSAFE"


def test_load_package_archive_rejects_duplicate_member_name() -> None:
    # 给定：ZIP 中央目录包含两个同名成员。
    archive_bytes = _archive_with_duplicate_member(_strict_package_files(), "package.yml")

    # 当/则：解析剧本包前拒绝有歧义的成员查找。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(archive_bytes)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_DUPLICATE_MEMBER"


def test_load_package_archive_rejects_unix_symlink_member() -> None:
    # 给定：Unix ZIP 成员声明为符号链接文件类型。
    archive_bytes = _archive_with_unix_member(stat.S_IFLNK, "assets/link")

    # 当/则：读取任何成员前拒绝符号链接。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(archive_bytes)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_SYMLINK_UNSUPPORTED"


def test_load_package_directory_rejects_symlink_before_copying_host_file(tmp_path: Path) -> None:
    # 给定：有效的松散剧本包包含指向根目录外文件的资源符号链接。
    package_dir = tmp_path / "package"
    write_package_directory(package_dir, _strict_package_files())
    outside = tmp_path / "host-secret.txt"
    outside.write_text("must not enter archive", encoding="utf-8")
    link = package_dir / "assets" / "host-secret.txt"
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except OSError as error:
        if os.name == "nt" and getattr(error, "winerror", None) == 1314:
            pytest.skip("Windows symlink privilege is unavailable")
        raise

    # 当/则：目录校验在打开目标文件前拒绝该链接。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_directory(package_dir)

    assert exc_info.value.code == "PACKAGE_DIRECTORY_SYMLINK_UNSUPPORTED"


def test_load_package_directory_enforces_budget_before_building_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：有效的松散剧本包超出刻意调小的文件数量预算。
    package_dir = tmp_path / "package"
    write_package_directory(package_dir, _strict_package_files())
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_ARCHIVE_FILES", 1)

    # 当/则：目录路径使用相同且稳定的归档预算错误。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_directory(package_dir)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_FILE_LIMIT_EXCEEDED"


@pytest.mark.parametrize(
    "file_type",
    (stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO, stat.S_IFSOCK),
)
def test_load_package_archive_rejects_unix_special_member(file_type: int) -> None:
    # 给定：Unix ZIP 成员声明为设备、FIFO 或套接字文件类型。
    archive_bytes = _archive_with_unix_member(file_type, "assets/special")

    # 当/则：只接受普通文件和目录。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(archive_bytes)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_MEMBER_TYPE_UNSUPPORTED"


@pytest.mark.parametrize(
    "path",
    (
        "character_scripts/player.md",
        "character_scripts/player/nested/chapter-01.md",
        "character_scripts/player/chapter-01.yml",
        "character_scripts/player/.md",
    ),
)
def test_load_package_archive_rejects_invalid_character_chapter_path(path: str) -> None:
    files: dict[str, str | bytes] = dict(_strict_package_files())
    files[path] = valid_character_chapter()

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_CHAPTER_PATH_UNSUPPORTED"


@pytest.mark.parametrize(
    "frontmatter_change",
    (
        ("chapter_id: chapter-01", "chapter_id: chapter-02"),
        ("character_id: player", "character_id: npc"),
    ),
)
def test_load_package_archive_rejects_character_chapter_path_id_mismatch(
    frontmatter_change: tuple[str, str],
) -> None:
    files = _strict_package_files()
    files["character_scripts/player/chapter-01.md"] = valid_character_chapter().replace(
        *frontmatter_change,
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_CHAPTER_PATH_INVALID"


@pytest.mark.parametrize(
    ("chapter", "expected_code"),
    (
        ("正文没有 frontmatter", "PACKAGE_CHARACTER_CHAPTER_FRONTMATTER_INVALID"),
        (
            "---\nchapter_id: chapter-01\n正文没有闭合分隔符",
            "PACKAGE_CHARACTER_CHAPTER_FRONTMATTER_INVALID",
        ),
        (
            valid_character_chapter().replace("\n章节正文。\n", "\n   \n"),
            "PACKAGE_CHARACTER_CHAPTER_BODY_REQUIRED",
        ),
        (
            valid_character_chapter().replace("title: 第一章", "title: 第一章\ntitle: 重复"),
            "PACKAGE_YAML_DUPLICATE_KEY",
        ),
        (
            valid_character_chapter().replace(
                "release:\n  type: game_start",
                "release: &release\n  type: game_start\nextra: *release",
            ),
            "PACKAGE_YAML_ALIAS_UNSUPPORTED",
        ),
        (
            valid_character_chapter().replace("order: 1", 'order: "1"'),
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            valid_character_chapter().replace("visibility: character_only", "visibility: public"),
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            valid_character_chapter().replace(
                "release:\n  type: game_start",
                "release: game_start",
            ),
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            valid_character_chapter().replace(
                "release:\n  type: game_start",
                "release:\n  type: scheduled",
            ),
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            valid_character_chapter().replace(
                "release:\n  type: game_start",
                "release:\n  type: rule",
            ),
            "INVALID_PACKAGE_SCHEMA",
        ),
        (
            valid_character_chapter().replace("title: 第一章", "title: 第一章\nunknown: true"),
            "INVALID_PACKAGE_SCHEMA",
        ),
    ),
)
def test_load_package_archive_rejects_invalid_character_chapter(
    chapter: str,
    expected_code: str,
) -> None:
    files = _strict_package_files()
    files["character_scripts/player/chapter-01.md"] = chapter

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == expected_code


def test_load_package_archive_rejects_invalid_character_chapter_encoding() -> None:
    files: dict[str, str | bytes] = dict(_strict_package_files())
    files["character_scripts/player/chapter-01.md"] = b"\xff"

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_CHAPTER_ENCODING_INVALID"


def test_load_package_archive_rejects_duplicate_character_chapter_id() -> None:
    files = _strict_package_files()
    files["character_scripts/player/chapter-01.md"] = valid_character_chapter()
    files["character_scripts/npc/chapter-01.md"] = valid_character_chapter().replace(
        "character_id: player",
        "character_id: npc",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_DUPLICATE_ID"
    assert "character chapter" in exc_info.value.message


@pytest.mark.parametrize(
    "change",
    (
        ("character_id: player", "character_id: ghost"),
        ("stage_min: prologue", "stage_min: ghost"),
    ),
)
def test_load_package_archive_rejects_unknown_character_chapter_reference(
    change: tuple[str, str],
) -> None:
    files = _strict_package_files()
    files["character_scripts/ghost/chapter-01.md"] = valid_character_chapter().replace(*change)
    if change[0] == "stage_min: prologue":
        files["character_scripts/player/chapter-01.md"] = files.pop(
            "character_scripts/ghost/chapter-01.md",
        )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


def test_load_package_archive_requires_matching_rule_chapter_event() -> None:
    files = minimal_package_files()
    files["character_scripts/player/chapter-01.md"] = valid_character_chapter().replace(
        "release:\n  type: game_start",
        "release:\n  type: rule\n  rule_id: chapter-rule",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_CHAPTER_RELEASE_INVALID"


def test_load_package_archive_accepts_matching_rule_chapter_event() -> None:
    files = minimal_package_files()
    files["character_scripts/player/chapter-01.md"] = valid_character_chapter().replace(
        "release:\n  type: game_start",
        "release:\n  type: rule\n  rule_id: chapter-rule",
    )
    prologue = files["stages/prologue.yml"]
    assert isinstance(prologue, str)
    files["stages/prologue.yml"] = (
        prologue
        + '\non_stage_entry:\n  - action: "unlock_character_chapter"\n'
        + '    event_id: "chapter-rule"\n    chapter_id: "chapter-01"\n'
    )

    package = load_package_archive(package_archive(files))

    assert package.chapters[0].release == {"type": "rule", "rule_id": "chapter-rule"}


def test_load_package_archive_rejects_oversized_character_chapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _strict_package_files()
    files["character_scripts/player/chapter-01.md"] = valid_character_chapter()
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_CHARACTER_CHAPTER_BYTES", 1)

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_CHARACTER_CHAPTER_TOO_LARGE"


def test_load_package_archive_rejects_invalid_yaml_encoding() -> None:
    # 给定：package.yml 不是有效的 UTF-8。
    files: dict[str, str | bytes] = dict(_strict_package_files())
    files["package.yml"] = b"\xff"

    # 当/则：解码失败转换为稳定的剧本包错误。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_ENCODING_INVALID"


def test_load_package_archive_rejects_invalid_yaml_syntax() -> None:
    # 给定：package.yml 包含格式错误的 YAML 语法。
    files = _strict_package_files()
    files["package.yml"] = "metadata: [unterminated"

    # 当/则：解析器失败转换为稳定的剧本包错误。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_SYNTAX_INVALID"


def test_load_package_archive_rejects_duplicate_yaml_key() -> None:
    # 给定：清单重复声明同一个字段，PyYAML 默认会用后值静默覆盖前值。
    files = _strict_package_files()
    files["package.yml"] += "\nmetadata:\n  id: overwritten\n"

    # 当/则：严格 YAML 边界在 schema 校验前拒绝含糊文档。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_DUPLICATE_KEY"


@pytest.mark.parametrize(
    "invalid_yaml",
    (
        "1: invalid\n",
        "metadata:\n  created_at: 2026-07-11T12:00:00Z\n",
        "metadata:\n  payload: !!binary aGVsbG8=\n",
    ),
)
def test_load_package_archive_rejects_non_json_yaml_types(invalid_yaml: str) -> None:
    # 给定：清单含非字符串键、时间戳或二进制值之一。
    files = _strict_package_files()
    files["package.yml"] = invalid_yaml

    # 当/则：严格 YAML 边界拒绝输入，不将非法类型转换为字符串。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_TYPE_INVALID"


def test_load_package_archive_rejects_yaml_alias_cycle() -> None:
    # 给定：小型 YAML 文档使用别名创建递归对象图。
    files = _strict_package_files()
    files["package.yml"] = "metadata: &root\n  id: minimal-case\n  title: test\n  loop: *root\n"

    # 当/则：在归一化递归前拒绝别名。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_ALIAS_UNSUPPORTED"


def test_load_package_archive_rejects_yaml_over_depth_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：解析器深度预算小于清单值的嵌套深度。
    files = _strict_package_files()
    files["package.yml"] = (
        "metadata:\n  id: minimal-case\n  title: test\nengine:\n  entry_stage: prologue\n"
    )
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_YAML_DEPTH", 1)

    # 当/则：事件扫描以稳定的复杂度错误失败。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_YAML_COMPLEXITY_EXCEEDED"


def test_load_package_archive_rejects_too_many_members(monkeypatch: pytest.MonkeyPatch) -> None:
    # 给定：配置的成员预算小于有效夹具的文件数量。
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_ARCHIVE_FILES", 1, raising=False)

    # 当/则：读取任何 YAML 成员前拒绝归档元数据。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(_strict_package_files()))

    assert exc_info.value.code == "PACKAGE_ARCHIVE_FILE_LIMIT_EXCEEDED"


def test_load_package_archive_rejects_oversized_member(monkeypatch: pytest.MonkeyPatch) -> None:
    # 给定：配置的单成员预算小于 package.yml 的大小。
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_MEMBER_BYTES", 1, raising=False)

    # 当/则：统一拒绝声明的成员未压缩大小。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(_strict_package_files()))

    assert exc_info.value.code == "PACKAGE_ARCHIVE_MEMBER_TOO_LARGE"


def test_load_package_archive_rejects_oversized_total(monkeypatch: pytest.MonkeyPatch) -> None:
    # 给定：配置的总解压预算小于夹具大小。
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_EXPANDED_BYTES", 1, raising=False)

    # 当/则：解压前拒绝未压缩总大小。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(_strict_package_files()))

    assert exc_info.value.code == "PACKAGE_ARCHIVE_EXPANDED_TOO_LARGE"


def test_load_package_archive_rejects_extreme_compression_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：deflate 归档超出刻意调小的解压比例预算。
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_COMPRESSION_RATIO", 1.0, raising=False)
    archive = _compressed_archive(_strict_package_files())

    # 当/则：仅使用 ZIP 元数据拒绝高压缩比成员。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(archive)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_COMPRESSION_RATIO_EXCEEDED"


def test_load_package_archive_rejects_oversized_compressed_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：核心加载器收到超过压缩输入预算的原始字节。
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_UPLOAD_BYTES", 8)

    # 当/则：在构造 ZipFile 前返回稳定的压缩大小错误。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(b"123456789")

    assert exc_info.value.code == "PACKAGE_ARCHIVE_COMPRESSED_TOO_LARGE"


def test_load_package_directory_stops_when_generated_zip_exceeds_compressed_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：目录内容有效，但生成 ZIP 的压缩字节预算被刻意调小。
    package_dir = tmp_path / "package"
    write_package_directory(package_dir, _strict_package_files())
    monkeypatch.setattr(package_archive_module, "MAX_PACKAGE_UPLOAD_BYTES", 64)

    # 当/则：有界缓冲区在生成过程中停止，不返回超限归档。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_directory(package_dir)

    assert exc_info.value.code == "PACKAGE_ARCHIVE_COMPRESSED_TOO_LARGE"


def _strict_package_files() -> dict[str, str]:
    return minimal_package_files()


def _compressed_archive(files: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _archive_with_duplicate_member(files: dict[str, str], duplicate_path: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
        with pytest.warns(UserWarning):
            archive.writestr(duplicate_path, files[duplicate_path])
    return buffer.getvalue()


def _archive_with_unix_member(file_type: int, path: str) -> bytes:
    buffer = BytesIO(package_archive(_strict_package_files()))
    member = ZipInfo(path)
    member.create_system = 3
    member.external_attr = (file_type | 0o600) << 16
    with ZipFile(buffer, "a") as archive:
        archive.writestr(member, b"target")
    return buffer.getvalue()
