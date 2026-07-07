import re
from collections.abc import Iterable
from typing import Final

from engine.core.package_archive import PackageArchiveError
from engine.core.package_asset_validation import (
    character_knowledge_warnings,
    validate_asset_paths,
)
from engine.core.package_dm_guide import validate_dm_guide
from engine.core.package_reference_validation import (
    validate_character_references,
    validate_clue_references,
    validate_ending_references,
    validate_evidence_references,
    validate_scene_references,
    validate_stage_references,
)
from engine.core.package_schema import ScriptPackageImport
from engine.core.package_validation_context import PackageValidationContext, ensure_reference
from engine.core.package_yaml import PackageManifest

PACKAGE_ID_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_package_import(
    package: ScriptPackageImport,
    available_files: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    manifest = PackageManifest.model_validate(package.package.config)
    _validate_package_id(manifest.metadata.id)
    context = _validation_context(package, available_files)

    ensure_reference("engine.entry_stage", manifest.engine.entry_stage, context.stage_ids)
    if manifest.engine.default_ending is not None:
        ensure_reference(
            "engine.default_ending",
            manifest.engine.default_ending,
            context.ending_ids,
        )

    validate_stage_references(package.stages, context)
    validate_character_references(package, context)
    validate_scene_references(package, context)
    validate_clue_references(package, context)
    validate_evidence_references(package, context)
    validate_ending_references(package, context)
    validate_asset_paths(package, manifest, context)
    validate_dm_guide(package, context)
    return character_knowledge_warnings(package, context)


def _validation_context(
    package: ScriptPackageImport,
    available_files: frozenset[str],
) -> PackageValidationContext:
    return PackageValidationContext(
        stage_ids=_unique_ids("stage", (stage.id for stage in package.stages)),
        character_ids=_unique_ids("character", (character.id for character in package.characters)),
        clue_ids=_unique_ids("clue", (clue.id for clue in package.clues)),
        evidence_ids=_unique_ids("evidence", (evidence.id for evidence in package.evidences)),
        scene_ids=_unique_ids("scene", (scene.id for scene in package.scenes)),
        media_ids=_unique_ids("media", (media.id for media in package.media_assets)),
        clue_round_ids=frozenset(clue.round_id for clue in package.clues),
        ending_ids=_unique_ids("ending", (ending.id for ending in package.endings)),
        available_files=available_files,
    )


def _validate_package_id(package_id: str) -> None:
    if PACKAGE_ID_PATTERN.fullmatch(package_id) is not None:
        return
    raise PackageArchiveError(
        "PACKAGE_ID_INVALID",
        f"metadata.id 必须使用小写字母、数字和连字符: {package_id}",
    )


def _unique_ids(kind: str, values: Iterable[str]) -> frozenset[str]:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise PackageArchiveError("PACKAGE_DUPLICATE_ID", f"重复的 {kind} id: {value}")
        seen.add(value)
    return frozenset(seen)
