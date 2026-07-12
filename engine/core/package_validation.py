"""提供共享的剧本包标识符和重复项校验辅助函数。"""

import re
from collections.abc import Iterable
from typing import Final

from engine.api.schemas.common import JsonValue
from engine.core.package_archive import PackageArchiveError
from engine.core.package_asset_validation import (
    character_knowledge_warnings,
    validate_asset_paths,
)
from engine.core.package_dm_guide import dm_guide_chain_ids, validate_dm_guide
from engine.core.package_reference_validation import (
    validate_character_references,
    validate_clue_references,
    validate_ending_references,
    validate_evidence_references,
    validate_scene_references,
    validate_stage_references,
)
from engine.core.package_schema import ScriptPackageImport
from engine.core.package_stage_index import stage_index_from_mapping
from engine.core.package_validation_context import PackageValidationContext, ensure_reference
from engine.core.package_yaml import PackageManifest

PACKAGE_ID_PATTERN: Final = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_package_import(
    package: ScriptPackageImport,
    available_files: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """校验剧本包标识、唯一性、引用、事件和 DM 指引。"""

    manifest_config = dict(package.package.config)
    manifest_config.pop("stage_index", None)
    manifest = PackageManifest.model_validate(manifest_config)
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
    stage_index = stage_index_from_mapping(package.stage_index)
    return PackageValidationContext(
        stage_ids=_unique_ids("stage", (stage.id for stage in package.stages)),
        act_ids=_unique_ids("act", (act.id for act in stage_index.acts)),
        character_ids=_unique_ids("character", (character.id for character in package.characters)),
        clue_ids=_unique_ids("clue", (clue.id for clue in package.clues)),
        evidence_ids=_unique_ids("evidence", (evidence.id for evidence in package.evidences)),
        scene_ids=_unique_ids("scene", (scene.id for scene in package.scenes)),
        media_ids=_unique_ids("media", (media.id for media in package.media_assets)),
        clue_round_ids=frozenset(clue.round_id for clue in package.clues),
        ending_ids=_unique_ids("ending", (ending.id for ending in package.endings)),
        available_files=available_files,
        card_ids=_card_ids(package),
        event_ids=_declared_event_ids(package),
        deduction_chain_ids=dm_guide_chain_ids(package.dm_guide),
    )


def _card_ids(package: ScriptPackageImport) -> frozenset[str]:
    return frozenset(
        evidence.id for evidence in package.evidences if evidence.type in {"prop", "skill_card"}
    )


def _declared_event_ids(package: ScriptPackageImport) -> frozenset[str]:
    event_ids: set[str] = set()
    for stage in package.stages:
        for field in ("on_stage_entry", "on_stage_exit"):
            _collect_event_ids(stage.definition.get(field), event_ids)
        for trigger_field in ("on_clue_discovered", "media_triggers"):
            triggers = stage.definition.get(trigger_field)
            if isinstance(triggers, list):
                for trigger in triggers:
                    if isinstance(trigger, dict):
                        _collect_event_ids(trigger.get("then"), event_ids)
    for scene in package.scenes:
        hotspots = scene.definition.get("hotspots")
        if isinstance(hotspots, list):
            for hotspot in hotspots:
                if isinstance(hotspot, dict):
                    _collect_event_ids(hotspot.get("on_click"), event_ids)
    for ending in package.endings:
        _collect_event_ids(list(ending.on_trigger), event_ids)
    return frozenset(event_ids)


def _collect_event_ids(value: JsonValue | None, event_ids: set[str]) -> None:
    if not isinstance(value, list):
        return
    for event in value:
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id != "":
            # 显式事件 ID 也是外部副作用的幂等键组成部分，因此必须在整个剧本包内唯一。
            if event_id in event_ids:
                raise PackageArchiveError(
                    "PACKAGE_DUPLICATE_ID",
                    f"重复的 event id: {event_id}",
                )
            event_ids.add(event_id)


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
