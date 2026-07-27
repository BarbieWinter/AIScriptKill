"""验证 Multiplayer v1 剧本包通过公开 loader 完整归一化。"""

from dataclasses import replace
from pathlib import Path

import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive, load_package_directory
from engine.core.package_multiplayer import multiplayer_package_playability
from engine.tests.package_loader_fixtures import (
    PackageFileContent,
    minimal_package_files,
    package_archive,
)

PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages"
FIXTURE_ROOT = PACKAGE_ROOT / "mp1-two-player"


def _fixture_files() -> dict[str, PackageFileContent]:
    files: dict[str, PackageFileContent] = {}
    for path in FIXTURE_ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(FIXTURE_ROOT).as_posix()
        if path.suffix in {".yml", ".yaml", ".md"}:
            files[relative] = path.read_text(encoding="utf-8")
        else:
            files[relative] = path.read_bytes()
    return files


def _text_file(files: dict[str, PackageFileContent], path: str) -> str:
    value = files[path]
    assert isinstance(value, str)
    return value


def test_load_real_two_player_package_preserves_normalized_multiplayer_authoring() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)

    assert package.package.id == "mp1-two-player"
    assert package.package.status == "published"
    assert package.package.config["multiplayer"] == {
        "min_players": 2,
        "max_players": 2,
        "character_assignment": "required",
        "start_policy": "all_players_ready",
        "duplicate_characters": False,
    }
    assert [stage.id for stage in package.stages] == ["investigation", "final-judgment"]
    assert {character.id for character in package.characters if character.is_playable} == {
        "investigator",
        "insider",
    }
    assert len(package.chapters) == 4

    investigation = package.stages[0].definition
    assert set(("chapters", "public_materials", "discussion", "settlement", "hints")) <= set(
        investigation
    )
    assert investigation["chapters"] == {
        "investigator": "investigator-investigation",
        "insider": "insider-investigation",
    }
    assert investigation["public_materials"] == [
        {"id": "arrival-photo", "reveal_at": "stage_enter"},
        {"id": "witness-note", "reveal_at": "all_players_read"},
    ]
    settlement = investigation["settlement"]
    assert isinstance(settlement, dict)
    assert settlement["mode"] == "secret_vote"
    assert settlement["tie_outcome_id"] == "split-vote"
    assert {option["outcome_id"] for option in settlement["options"]} == {
        "trust-investigator",
        "trust-insider",
    }
    assert len(investigation["hints"][0]["levels"]) == 3

    final_settlement = package.stages[1].definition["settlement"]
    assert isinstance(final_settlement, dict)
    assert final_settlement["mode"] == "final_judgment"
    assert final_settlement["answer_mode"] == "shared_choice"
    assert final_settlement["tie_outcome_id"] is None
    assert final_settlement["submission_change"] == "allowed_before_complete"
    assert final_settlement["reveal"] == "outcome_only"
    assert final_settlement["ending_by_outcome"] == {
        "conflicting-accounts": "conflicting-accounts",
        "insufficient-evidence": "insufficient-evidence",
    }
    playability = multiplayer_package_playability(package)
    assert playability.playable is True
    assert playability.diagnostics == ()
    assert playability.terminal_stage_id == "final-judgment"
    assert tuple(
        (resolution.outcome_id, resolution.ending_id)
        for resolution in playability.ending_resolutions
    ) == (
        ("conflicting-accounts", "conflicting-accounts"),
        ("insufficient-evidence", "insufficient-evidence"),
    )
    assert {ending.id for ending in package.endings} == {
        "insufficient-evidence",
        "conflicting-accounts",
    }
    assert package.stages[1].definition["public_materials"] == [
        {"id": "case-reconstruction", "reveal_at": "settlement_done"},
        {"id": "limited-finding", "reveal_at": "outcome:conflicting-accounts"},
        {"id": "unsupported-finding", "reveal_at": "outcome:insufficient-evidence"},
    ]
    truth = package.dm_guide["truth"]
    assert isinstance(truth, dict)
    assert "知情人于二十点零五分违规使用备用钥匙" in str(truth)

    insider_chapter = next(
        chapter for chapter in package.chapters if chapter.id == "insider-investigation"
    )
    assert "是否承认违规进入由你决定" in insider_chapter.content
    public_text = str(package.package.config) + "".join(
        str(stage.definition) + str(character.definition)
        for stage, character in zip(
            package.stages,
            package.characters,
            strict=True,
        )
    )
    assert "是否承认违规进入由你决定" not in public_text


def test_legacy_packages_skip_multiplayer_validation_and_keep_stage_shape() -> None:
    package = load_package_directory(PACKAGE_ROOT / "snow-village")

    assert package.package.id == "snow-village"
    assert "multiplayer" not in package.package.config
    assert all("chapters" not in stage.definition for stage in package.stages)


def test_legacy_package_rejects_flat_multiplayer_stage_fields_without_policy() -> None:
    files = minimal_package_files()
    files["stages/prologue.yml"] += "\nhints: []\n"

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "hints" in exc_info.value.message


def test_multiplayer_policy_requires_all_flat_fields_on_every_stage() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        "hints: []\n", ""
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "hints" in exc_info.value.message


def test_multiplayer_manifest_and_info_player_ranges_must_match() -> None:
    files = _fixture_files()
    files["package.yml"] = _text_file(files, "package.yml").replace(
        "  max_players: 2\n",
        "  max_players: 3\n",
        1,
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_PLAYER_RANGE_INVALID"


def test_multiplayer_package_requires_enough_playable_characters() -> None:
    files = _fixture_files()
    files["characters/_index.yml"] = _text_file(files, "characters/_index.yml").replace(
        '  - id: "insider"\n    name: "知情人"\n    playable: true',
        '  - id: "insider"\n    name: "知情人"\n    playable: false',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_PLAYER_COUNT_INVALID"


@pytest.mark.parametrize(
    ("old", "new", "expected_message"),
    (
        (
            'insider: "insider-investigation"',
            'insider: "missing-chapter"',
            "missing-chapter",
        ),
        (
            'insider: "insider-investigation"',
            'insider: "investigator-investigation"',
            "不属于角色 insider",
        ),
    ),
)
def test_multiplayer_stage_chapters_validate_existence_and_owner(
    old: str,
    new: str,
    expected_message: str,
) -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        old, new
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert expected_message in exc_info.value.message


def test_multiplayer_stage_chapters_cover_every_playable_character() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        '  insider: "insider-investigation"\n', ""
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "缺少=['insider']" in exc_info.value.message


def test_public_material_must_exist_in_clue_evidence_or_media_namespace() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'id: "witness-note"', 'id: "unknown-material"'
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "unknown-material" in exc_info.value.message


def test_public_material_namespaces_must_be_disjoint() -> None:
    files = _fixture_files()
    files["media/materials.yml"] = _text_file(files, "media/materials.yml").replace(
        'id: "arrival-photo"',
        'id: "witness-note"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_DUPLICATE_ID"
    assert "clue/media" in exc_info.value.message
    assert "witness-note" in exc_info.value.message


def test_outcome_material_trigger_resolves_only_within_its_stage() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'reveal_at: "all_players_read"', 'reveal_at: "outcome:insufficient-evidence"'
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "insufficient-evidence" in exc_info.value.message


def test_outcome_material_trigger_accepts_option_and_tie_outcomes_from_same_stage() -> None:
    for outcome_id in ("trust-insider", "split-vote"):
        files = _fixture_files()
        files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
            'reveal_at: "all_players_read"', f'reveal_at: "outcome:{outcome_id}"'
        )

        package = load_package_archive(package_archive(files))

        investigation = package.stages[0].definition
        assert investigation["public_materials"][1]["reveal_at"] == f"outcome:{outcome_id}"


def test_final_judgment_must_be_the_terminal_stage() -> None:
    files = _fixture_files()
    files["stages/_index.yml"] = _text_file(files, "stages/_index.yml").replace(
        '    sort_order: 0\n  - id: "final-judgment"\n    name: "共同终判"\n    sort_order: 10',
        '    sort_order: 10\n  - id: "final-judgment"\n    name: "共同终判"\n    sort_order: 0',
    )
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        "sort_order: 0", "sort_order: 10"
    )
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        "sort_order: 10", "sort_order: 0"
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_TERMINAL_STAGE_INVALID"
    assert exc_info.value.message == "多人剧本必须且只能以一个 final_judgment 阶段结束"


def test_final_judgment_requires_supported_terminal_effect() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        '  default_effect: "branch"', '  default_effect: "record_and_continue"'
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_TERMINAL_EFFECT_UNSUPPORTED"
    assert exc_info.value.message == "最终判断必须使用 branch 终局效果"


def test_nonterminal_stage_requires_supported_continue_effect() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        '  default_effect: "record_and_continue"', '  default_effect: "branch"'
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_STAGE_EFFECT_UNSUPPORTED"
    assert exc_info.value.message == "非终局阶段只支持 record_and_continue 效果"


def test_playability_diagnostic_identifies_unknown_mapped_ending() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    final_stage = package.stages[-1]
    definition = dict(final_stage.definition)
    settlement = dict(definition["settlement"])
    settlement["ending_by_outcome"] = {
        "conflicting-accounts": "missing-ending",
        "insufficient-evidence": "insufficient-evidence",
    }
    definition["settlement"] = settlement
    invalid = replace(
        package,
        stages=(*package.stages[:-1], replace(final_stage, definition=definition)),
    )

    playability = multiplayer_package_playability(invalid)

    assert playability.playable is False
    assert len(playability.diagnostics) == 1
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_ENDING_REFERENCE_INVALID"
    assert diagnostic.stage_id == "final-judgment"
    assert diagnostic.outcome_id == "conflicting-accounts"
    assert diagnostic.ending_id == "missing-ending"
    assert diagnostic.field == (
        "stages.final-judgment.settlement.ending_by_outcome.conflicting-accounts"
    )


def test_final_judgment_requires_complete_outcome_to_ending_mapping() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        '    insufficient-evidence: "insufficient-evidence"\n', ""
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_ENDING_MAPPING_MISSING"
    assert exc_info.value.message == ("最终判断结果缺少结局映射: insufficient-evidence")


def test_shared_final_judgment_forbids_tie_outcome() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        '  reveal: "outcome_only"',
        '  tie_outcome_id: "final-tie"\n  reveal: "outcome_only"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "tie outcome" in exc_info.value.message


def test_multiplayer_playability_requires_exactly_two_playable_roles() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    observer = replace(
        package.characters[0],
        id="observer",
        name="旁观者",
        sort_order=20,
    )

    playability = multiplayer_package_playability(
        replace(package, characters=(*package.characters, observer))
    )

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_PLAYER_COUNT_INVALID"
    assert diagnostic.field == "characters.playable"


def test_multiplayer_playability_requires_frozen_truth_content() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)

    playability = multiplayer_package_playability(replace(package, dm_guide={}))

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_TRUTH_REQUIRED"
    assert diagnostic.field == "dm_guide.truth"


def test_multiplayer_truth_requires_nonempty_case_summary() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    dm_guide = dict(package.dm_guide)
    truth_file = dict(dm_guide["truth"])
    truth = dict(truth_file["truth"])
    truth["case_summary"] = " "
    truth_file["truth"] = truth
    dm_guide["truth"] = truth_file

    playability = multiplayer_package_playability(replace(package, dm_guide=dm_guide))

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_TRUTH_CONTENT_REQUIRED"
    assert diagnostic.field == "dm_guide.truth.truth.case_summary"


def test_shared_final_judgment_requires_outcome_only_reveal() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        '  reveal: "outcome_only"', '  reveal: "named_ballots"'
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_FINAL_REVEAL_UNSUPPORTED"
    assert exc_info.value.message == "shared_choice 最终判断只支持 outcome_only 揭晓"


@pytest.mark.parametrize(
    ("mutation", "expected_code", "expected_field"),
    (
        (
            "condition",
            "PACKAGE_MULTIPLAYER_ENDING_CONDITION_UNSUPPORTED",
            "endings.conflicting-accounts.condition",
        ),
        (
            "actions",
            "PACKAGE_MULTIPLAYER_ENDING_ACTIONS_UNSUPPORTED",
            "endings.conflicting-accounts.on_trigger",
        ),
    ),
)
def test_multiplayer_endings_reject_ignored_legacy_behavior(
    mutation: str,
    expected_code: str,
    expected_field: str,
) -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    ending = package.endings[0]
    if mutation == "condition":
        invalid_ending = replace(ending, condition={"type": "stage_reached", "stage": "x"})
    else:
        invalid_ending = replace(ending, on_trigger=({"action": "show_truth_summary"},))

    playability = multiplayer_package_playability(
        replace(package, endings=(invalid_ending, *package.endings[1:]))
    )

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == expected_code
    assert diagnostic.field == expected_field
    assert diagnostic.ending_id == "conflicting-accounts"


def test_multiplayer_endings_reject_ignored_rating_bonus() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    ending = package.endings[0]
    invalid_ending = replace(
        ending,
        metadata={**ending.metadata, "rating_bonus": {"deduction": 10}},
    )

    playability = multiplayer_package_playability(
        replace(package, endings=(invalid_ending, *package.endings[1:]))
    )

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_ENDING_RATING_UNSUPPORTED"
    assert diagnostic.field == "endings.conflicting-accounts.rating_bonus"
    assert diagnostic.ending_id == "conflicting-accounts"


def test_multiplayer_rejects_legacy_default_ending() -> None:
    files = _fixture_files()
    files["package.yml"] = _text_file(files, "package.yml").replace(
        '  entry_stage: "investigation"',
        '  entry_stage: "investigation"\n  default_ending: "conflicting-accounts"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_DEFAULT_ENDING_UNSUPPORTED"
    assert exc_info.value.message == "多人终局不支持 engine.default_ending"


def test_multiplayer_entry_stage_must_match_first_ordered_stage() -> None:
    package = load_package_directory(FIXTURE_ROOT, publish=True)
    config = dict(package.package.config)
    engine = dict(config["engine"])
    engine["entry_stage"] = "final-judgment"
    config["engine"] = engine
    invalid = replace(package, package=replace(package.package, config=config))

    playability = multiplayer_package_playability(invalid)

    assert playability.playable is False
    diagnostic = playability.diagnostics[0]
    assert diagnostic.code == "PACKAGE_MULTIPLAYER_ENTRY_STAGE_INVALID"
    assert diagnostic.field == "package.engine.entry_stage"
    assert diagnostic.stage_id == "final-judgment"


def test_multiplayer_stage_order_must_be_unambiguous() -> None:
    files = _fixture_files()
    files["stages/_index.yml"] = _text_file(files, "stages/_index.yml").replace(
        "    sort_order: 10", "    sort_order: 0"
    )
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        "sort_order: 10", "sort_order: 0"
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_STAGE_ORDER_INVALID"
    assert exc_info.value.message == "多人阶段 sort_order 必须唯一"


def test_multiplayer_act_stage_order_must_match_linear_order() -> None:
    files = _fixture_files()
    files["stages/_index.yml"] = _text_file(files, "stages/_index.yml").replace(
        'stages: ["investigation", "final-judgment"]',
        'stages: ["final-judgment", "investigation"]',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_ACT_ORDER_INVALID"
    assert exc_info.value.message == "多人 act 阶段声明必须与线性 stage 顺序一致"


def test_multiplayer_transitions_must_match_linear_executor() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'allowed_transitions: ["final-judgment"]', "allowed_transitions: []"
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_TRANSITION_UNSUPPORTED"
    assert exc_info.value.message == "多人阶段 transition 必须只指向线性下一阶段"


def test_multiplayer_stage_conditions_must_be_empty() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        "entry_conditions: []",
        'entry_conditions:\n  - type: "stage_completed"\n    stage_id: "final-judgment"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_CONDITIONS_UNSUPPORTED"
    assert exc_info.value.message == "线性多人 executor 不支持阶段 entry/exit conditions"


def test_later_multiplayer_chapter_requires_matching_stage_enter_release() -> None:
    files = _fixture_files()
    path = "character_scripts/investigator/investigator-final-judgment.md"
    files[path] = _text_file(files, path).replace(
        "release:\n  type: stage_enter\n  stage_id: final-judgment",
        "release:\n  type: game_start",
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_CHAPTER_RELEASE_INVALID"
    assert exc_info.value.message == ("角色 investigator 的阶段 final-judgment 章节授权声明不匹配")


def test_multiplayer_stages_cannot_reuse_character_chapters() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        'investigator: "investigator-final-judgment"',
        'investigator: "investigator-investigation"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_CHAPTER_REUSED"
    assert exc_info.value.message == "角色章节不能跨多人阶段复用: investigator-investigation"


def test_multiplayer_rejects_unreferenced_playable_chapter() -> None:
    files = _fixture_files()
    source = "character_scripts/investigator/investigator-final-judgment.md"
    files["character_scripts/investigator/investigator-epilogue.md"] = (
        _text_file(files, source)
        .replace("chapter_id: investigator-final-judgment", "chapter_id: investigator-epilogue")
        .replace("order: 2", "order: 3")
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_CHAPTER_UNREFERENCED"
    assert exc_info.value.message == ("可玩角色章节未映射到多人阶段: investigator-epilogue")


@pytest.mark.parametrize("field", ("allow_stage_jump", "allow_stage_regression"))
def test_multiplayer_rejects_unsupported_navigation_flags(field: str) -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'allowed_transitions: ["final-judgment"]',
        f'allowed_transitions: ["final-judgment"]\n{field}: true',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_NAVIGATION_UNSUPPORTED"
    assert exc_info.value.message == "线性多人 executor 不支持阶段跳跃或回退"


def test_multiplayer_stage_cast_must_match_playable_roles() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'available_characters: ["investigator", "insider"]',
        'available_characters: ["investigator"]',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_STAGE_CAST_INVALID"
    assert exc_info.value.message == "多人阶段 available_characters 必须恰好覆盖可玩角色"


def test_multiplayer_rejects_ignored_stage_capabilities() -> None:
    files = _fixture_files()
    files["stages/investigation.yml"] = _text_file(files, "stages/investigation.yml").replace(
        'available_characters: ["investigator", "insider"]',
        'available_characters: ["investigator", "insider"]\nspecial_rules:\n  hidden: true',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_MULTIPLAYER_STAGE_CAPABILITY_UNSUPPORTED"
    assert exc_info.value.message == "线性多人 executor 不支持该阶段 legacy capability"
