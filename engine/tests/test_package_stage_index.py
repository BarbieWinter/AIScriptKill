import pytest

from engine.core.package_archive import PackageArchiveError
from engine.core.package_loader import load_package_archive
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


def test_load_package_archive_rejects_missing_stage_index() -> None:
    # Given: stages/_index.yml is absent even though stage files exist.
    files = minimal_package_files()
    files.pop("stages/_index.yml")

    # When / Then: the package is rejected before import.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_STAGE_INDEX_REQUIRED"


def test_load_package_archive_rejects_stage_index_missing_stage_yaml() -> None:
    # Given: stages/_index.yml declares a stage with no matching stage YAML.
    files = minimal_package_files()
    files["stages/_index.yml"] = """
stages:
  - id: "prologue"
    name: "序章"
    sort_order: 0
  - id: "act1"
    name: "第一幕"
    sort_order: 10
  - id: "missing_review"
    name: "复盘"
    sort_order: 20
"""

    # When / Then: the mismatch is reported explicitly.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_STAGE_INDEX_INVALID"
    assert "missing_review" in exc_info.value.message


def test_load_package_archive_rejects_stage_yaml_not_declared_in_index() -> None:
    # Given: one stage file is present but not declared in stages/_index.yml.
    files = minimal_package_files()
    files["stages/_index.yml"] = """
stages:
  - id: "prologue"
    name: "序章"
    sort_order: 0
  - id: "act1"
    name: "第一幕"
    sort_order: 10
"""

    # When / Then: the unindexed stage file is rejected.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_STAGE_INDEX_INVALID"
    assert "review" in exc_info.value.message


def test_load_package_archive_rejects_stage_index_act_with_unknown_stage() -> None:
    # Given: an act references a stage absent from the index's stage list.
    files = minimal_package_files()
    files["stages/_index.yml"] = (
        f"{files['stages/_index.yml']}\n"
        '  - id: "broken"\n'
        '    name: "坏分组"\n'
        '    stages: ["ghost"]\n'
    )

    # When / Then: act references are validated against the index.
    with pytest.raises(PackageArchiveError) as exc_info:
        load_package_archive(package_archive(files))

    assert exc_info.value.code == "PACKAGE_STAGE_INDEX_INVALID"
    assert "ghost" in exc_info.value.message
