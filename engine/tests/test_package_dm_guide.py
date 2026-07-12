import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


def test_load_package_archive_keeps_dm_guide_out_of_public_config() -> None:
    # 给定：dm_guide 包含阶段注释和仅供真相流程使用的结局资源。
    files = _package_files_with_dm_guide()

    # 当：加载剧本包。
    package = load_package_archive(package_archive(files))

    # 则：dm_guide 仍可供特权导入使用，但不会进入公共配置。
    stage_notes_file = package.dm_guide["stage_notes"]
    assert isinstance(stage_notes_file, dict)
    stage_notes = stage_notes_file["stage_notes"]
    assert isinstance(stage_notes, list)
    first_note = stage_notes[0]
    assert isinstance(first_note, dict)
    assert first_note["stage_id"] == "prologue"
    assert "dm_guide" not in package.package.config


def test_load_package_archive_rejects_dm_guide_unknown_stage_note() -> None:
    # 给定：DM 阶段注释引用了 stages/_index.yml 中不存在的阶段。
    files = _package_files_with_dm_guide()
    files["dm_guide/stage_notes.yml"] = _text_file(
        files,
        "dm_guide/stage_notes.yml",
    ).replace(
        'stage_id: "prologue"',
        'stage_id: "ghost"',
    )

    # 当/则：导入时校验特权指引引用。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_unknown_dm_dialogue_phase() -> None:
    # 给定：关键台词绑定到剧本包中不存在的演出阶段。
    files = _package_files_with_dm_guide()
    files["dm_guide/performance_guide.yml"] = _text_file(
        files,
        "dm_guide/performance_guide.yml",
    ).replace('phase: "prologue"', 'phase: "ghost"')

    # 当/则：私有演出内容与公开阶段使用同一权威阶段索引。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "key_dialogue_lines phase" in exc_info.value.message
    assert "ghost" in exc_info.value.message


@pytest.mark.parametrize("field", ("murderer", "victim"))
def test_load_package_archive_rejects_unknown_truth_character(field: str) -> None:
    # 给定：案件真相中的核心角色并未在 characters/ 中声明。
    files = _package_files_with_dm_guide()
    files["dm_guide/truth.yml"] = _text_file(files, "dm_guide/truth.yml").replace(
        f'{field}: "npc"' if field == "murderer" else f'{field}: "player"',
        f'{field}: "ghost"',
    )

    # 当/则：导入边界拒绝悬空的真相角色引用。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert field in exc_info.value.message
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_unknown_truth_evidence_chain_member() -> None:
    # 给定：关键证据链包含 evidences/ 中不存在的证物。
    files = _package_files_with_dm_guide()
    files["dm_guide/truth.yml"] = _text_file(files, "dm_guide/truth.yml").replace(
        "clue_2",
        "missing_evidence",
    )

    # 当/则：导入边界拒绝悬空的证据链节点。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "key_evidence_chain" in exc_info.value.message
    assert "missing_evidence" in exc_info.value.message


def test_load_package_archive_accepts_declared_condition_references() -> None:
    # 给定：条件引用的证物、卡牌、事件和主推理链均已在包内声明。
    files = _package_files_with_condition_references()

    # 当：导入完整剧本包。
    package = load_package_archive(package_archive(files))

    # 则：全部跨文件引用通过校验。
    assert package.package.id == "minimal-case"


@pytest.mark.parametrize(
    ("old", "new", "missing_id"),
    (
        ('evidence_ids: ["clue_1"]', 'evidence_ids: ["missing_evidence"]', "missing_evidence"),
        ('card_id: "card_1"', 'card_id: "missing_card"', "missing_card"),
        ('event_id: "broadcast_1"', 'event_id: "missing_event"', "missing_event"),
        ('event_id: "broadcast_2"', 'event_id: "missing_event"', "missing_event"),
        ('chain_id: "main"', 'chain_id: "missing_chain"', "missing_chain"),
    ),
)
def test_load_package_archive_rejects_unknown_condition_reference(
    old: str,
    new: str,
    missing_id: str,
) -> None:
    # 给定：一个条件引用了对应权威索引中不存在的 ID。
    files = _package_files_with_condition_references()
    files["stages/prologue.yml"] = _text_file(files, "stages/prologue.yml").replace(old, new, 1)

    # 当/则：导入边界拒绝会永久无法成立的条件。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert missing_id in exc_info.value.message


def test_load_package_archive_rejects_duplicate_explicit_event_id() -> None:
    # 给定：两个不同事件声明复用了同一个显式 ID，会产生相同的外部幂等键。
    files = _package_files_with_condition_references()
    files["stages/prologue.yml"] = _text_file(files, "stages/prologue.yml").replace(
        '    event_id: "broadcast_2"\n    text: "第二段广播"',
        '    event_id: "broadcast_1"\n    text: "第二段广播"',
    )

    # 当/则：剧本包在运行前拒绝含糊的事件身份，而不是跳过第二个动作。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_DUPLICATE_ID"
    assert "broadcast_1" in exc_info.value.message


def test_load_package_archive_rejects_dm_guide_missing_truth_asset() -> None:
    # 给定：dm_guide 真相资料引用了不存在的本地音频文件。
    files = _package_files_with_dm_guide()
    files.pop("assets/audio/ending.mp3")

    # 当/则：缺失的特权媒体与其他剧本包资源一样上报。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_ASSET_MISSING"
    assert "assets/audio/ending.mp3" in exc_info.value.message


def test_load_package_archive_rejects_unknown_dm_guide_file() -> None:
    # 给定：受支持的 DM 指引文件名拼写错误。
    files = _package_files_with_dm_guide()
    files["dm_guide/trutth.yml"] = "truth: {}\n"

    # 当/则：导入边界拒绝未知的顶层指引键。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "trutth" in exc_info.value.message


def test_load_package_archive_rejects_misspelled_truth_field() -> None:
    # 给定：truth.yml 中已记录的字段拼写错误。
    files = _package_files_with_dm_guide()
    files["dm_guide/truth.yml"] = _text_file(files, "dm_guide/truth.yml").replace(
        "case_summary",
        "case_summray",
    )

    # 当/则：导入时严格解析嵌套的仅限 DM 内容。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "case_summray" in exc_info.value.message


def test_load_package_archive_rejects_string_dm_guide_boolean() -> None:
    # 给定：truth.timeline[].hidden 使用可强制转换的字符串而非布尔值。
    files = _package_files_with_dm_guide()
    files["dm_guide/truth.yml"] = _text_file(files, "dm_guide/truth.yml").replace(
        "hidden: true",
        'hidden: "true"',
    )

    # 当/则：严格 DM 指引模型拒绝错误的标量类型。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "hidden" in exc_info.value.message


@pytest.mark.parametrize(
    "unsupported_path",
    ("dm_guide/nested/truth.yml", "dm_guide/truth.yaml"),
)
def test_load_package_archive_rejects_dm_guide_path_alias(unsupported_path: str) -> None:
    # 给定：DM 指引内容使用嵌套路径或文档未约定的 .yaml 别名。
    files = _package_files_with_dm_guide()
    files[unsupported_path] = _text_file(files, "dm_guide/truth.yml")

    # 当/则：只接受文档约定的根级 .yml 路径。
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_DM_GUIDE_PATH_UNSUPPORTED"


def _package_files_with_dm_guide() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = dict(minimal_package_files())
    files["dm_guide/stage_notes.yml"] = """
stage_notes:
  - stage_id: "prologue"
    dm_behavior: "正常开场"
    notes: "提醒玩家进入序章。"
    atmosphere: "平静"
    key_moments:
      - action: "player_reading_done"
        dm_action: "提醒玩家开始"
    prop_usage: ["信封"]
    trap_mechanics: ["误导"]
"""
    files["dm_guide/truth.yml"] = """
truth:
  case_summary: "测试真相"
  murderer: "npc"
  victim: "player"
  motive: "测试"
  timeline:
    - time: "20:00"
      event: "事件发生"
      hidden: true
  key_evidence_chain: ["clue_1 -> clue_2"]
  alternative_endings:
    - id: "ending_caught"
      condition: "player_correct_all"
      news_broadcast: "assets/audio/ending.mp3"
"""
    files["dm_guide/performance_guide.yml"] = """
performance:
  dm_split_personality:
    phase_1:
      character: "正常DM"
      actor: "DM1"
      traits: ["专业"]
      pre_broadcast: "平静"
      post_broadcast: "紧张"
  key_dialogue_lines:
    - phase: "prologue"
      line: "欢迎来到测试剧本。"
      emotion: "平静"
"""
    files["evidences/clue_1.yml"] = _evidence_file("clue_1", "key_evidence")
    files["evidences/clue_2.yml"] = _evidence_file("clue_2", "key_evidence")
    files["assets/audio/ending.mp3"] = b"ending"
    return files


def _package_files_with_condition_references() -> dict[str, str | bytes]:
    files = _package_files_with_dm_guide()
    files["evidences/card_1.yml"] = _evidence_file("card_1", "prop")
    files["stages/prologue.yml"] = _text_file(files, "stages/prologue.yml").replace(
        "exit_conditions: []",
        '''exit_conditions:
  - type: "key_evidence_used"
    evidence_ids: ["clue_1"]
  - type: "player_used_card"
    card_id: "card_1"
  - type: "event_triggered"
    event_id: "broadcast_1"
  - type: "event_not_triggered"
    event_id: "broadcast_2"
  - type: "deduction_chain_complete"
    chain_id: "main"
on_stage_entry:
  - action: "dm_narrate"
    event_id: "broadcast_1"
    text: "第一段广播"
  - action: "dm_narrate"
    event_id: "broadcast_2"
    text: "第二段广播"''',
    )
    return files


def _evidence_file(evidence_id: str, evidence_type: str) -> str:
    return f"""
id: "{evidence_id}"
name: "测试证物 {evidence_id}"
type: "{evidence_type}"
description:
  surface: "用于跨引用校验。"
discovery:
  scene_id: "main_hall"
  stage_visible: "prologue"
"""


def _text_file(files: dict[str, str | bytes], path: str) -> str:
    content = files[path]
    assert isinstance(content, str)
    return content
