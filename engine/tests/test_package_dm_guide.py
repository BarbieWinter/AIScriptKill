import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


def test_load_package_archive_keeps_dm_guide_out_of_public_config() -> None:
    # Given: dm_guide contains stage notes and a truth-only ending asset.
    files = _package_files_with_dm_guide()

    # When: the package is loaded.
    package = load_package_archive(package_archive(files))

    # Then: dm_guide remains available for privileged import without entering public config.
    assert package.dm_guide["stage_notes"]["stage_notes"][0]["stage_id"] == "prologue"
    assert "dm_guide" not in package.package.config


def test_load_package_archive_rejects_dm_guide_unknown_stage_note() -> None:
    # Given: a DM stage note references a stage that is not in stages/_index.yml.
    files = _package_files_with_dm_guide()
    files["dm_guide/stage_notes.yml"] = files["dm_guide/stage_notes.yml"].replace(
        'stage_id: "prologue"',
        'stage_id: "ghost"',
    )

    # When / Then: privileged guide references are validated at import time.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_REFERENCE_INVALID"
    assert "ghost" in exc_info.value.message


def test_load_package_archive_rejects_dm_guide_missing_truth_asset() -> None:
    # Given: dm_guide truth references a local audio file that is absent.
    files = _package_files_with_dm_guide()
    files.pop("assets/audio/ending.mp3")

    # When / Then: missing privileged media is reported like other package assets.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_ASSET_MISSING"
    assert "assets/audio/ending.mp3" in exc_info.value.message


def _package_files_with_dm_guide() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = minimal_package_files()
    files["dm_guide/stage_notes.yml"] = """
stage_notes:
  - stage_id: "prologue"
    dm_behavior: "正常开场"
    notes: "提醒玩家进入序章。"
"""
    files["dm_guide/truth.yml"] = """
truth:
  case_summary: "测试真相"
  alternative_endings:
    - id: "ending_caught"
      condition: "player_correct_all"
      news_broadcast: "assets/audio/ending.mp3"
"""
    files["assets/audio/ending.mp3"] = b"ending"
    return files
