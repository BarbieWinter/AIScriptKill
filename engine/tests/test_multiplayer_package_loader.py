"""验证 Multiplayer v1 剧本包通过公开 loader 完整归一化。"""

from pathlib import Path

import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive, load_package_directory
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

    insider_chapter = next(
        chapter for chapter in package.chapters if chapter.id == "insider-investigation"
    )
    assert "你可以隐瞒自己提前读过值班记录这一事实" in insider_chapter.content
    public_text = str(package.package.config) + "".join(
        str(stage.definition) + str(character.definition)
        for stage, character in zip(
            package.stages,
            package.characters,
            strict=True,
        )
    )
    assert "你可以隐瞒自己提前读过值班记录这一事实" not in public_text


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


def test_shared_final_judgment_forbids_tie_outcome() -> None:
    files = _fixture_files()
    files["stages/final-judgment.yml"] = _text_file(files, "stages/final-judgment.yml").replace(
        '  reveal: "named_ballots"',
        '  tie_outcome_id: "final-tie"\n  reveal: "named_ballots"',
    )

    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "INVALID_PACKAGE_SCHEMA"
    assert "tie outcome" in exc_info.value.message
