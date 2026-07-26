"""连接 Multiplayer v1 创作契约、严格剧本包 loader 与 MP-2 运行时策略。"""

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Final, Literal, cast

from pydantic import ValidationError

from engine.contracts.multiplayer_v1.authoring import (
    MULTIPLAYER_STAGE_ADAPTER,
    FinalJudgmentSettlementDefinition,
    MultiplayerStageDefinition,
    SecretVoteSettlementDefinition,
    SharedChoiceSettlementDefinition,
)
from engine.contracts.multiplayer_v1.vocabulary import SettlementEffect
from engine.core.package_archive import PackageArchiveError
from engine.core.package_manifest_yaml import PackageManifest
from engine.core.package_schema import JsonMapping, ScriptPackageImport, StageRecord
from engine.core.package_stage_index import stage_index_from_mapping
from engine.core.package_validation_context import ensure_reference

MULTIPLAYER_STAGE_KEYS: Final[frozenset[str]] = frozenset(
    ("chapters", "public_materials", "discussion", "settlement", "hints")
)


def split_stage_mapping(
    raw: JsonMapping,
    multiplayer_enabled: bool,
) -> tuple[JsonMapping, JsonMapping]:
    """拆出平铺的多人阶段字段，并经 JSON 边界归一化严格契约。"""

    present_keys = MULTIPLAYER_STAGE_KEYS.intersection(raw)
    if not multiplayer_enabled:
        return raw, {}
    if present_keys != MULTIPLAYER_STAGE_KEYS:
        missing = ", ".join(sorted(MULTIPLAYER_STAGE_KEYS.difference(present_keys)))
        raise PackageArchiveError(
            "INVALID_PACKAGE_SCHEMA",
            f"multiplayer stage {raw.get('id', '<unknown>')} 缺少必需字段: {missing}",
        )

    multiplayer_raw: JsonMapping = {"id": raw.get("id")}
    for key in MULTIPLAYER_STAGE_KEYS:
        multiplayer_raw[key] = raw[key]
    stage = MULTIPLAYER_STAGE_ADAPTER.validate_json(json.dumps(multiplayer_raw, ensure_ascii=False))
    normalized = cast(
        JsonMapping,
        MULTIPLAYER_STAGE_ADAPTER.dump_python(stage, mode="json"),
    )
    legacy = {key: value for key, value in raw.items() if key not in MULTIPLAYER_STAGE_KEYS}
    return legacy, normalized


def _validate_multiplayer_content(
    package: ScriptPackageImport,
    manifest: PackageManifest,
) -> None:
    """校验多人策略、角色章节、公共材料与阶段局部结果引用。"""

    policy = manifest.multiplayer
    if policy is None:
        return
    if (
        manifest.info.min_players != policy.min_players
        or manifest.info.max_players != policy.max_players
    ):
        raise PackageArchiveError(
            "PACKAGE_MULTIPLAYER_PLAYER_RANGE_INVALID",
            "package.yml info 与 multiplayer 的 min_players/max_players 必须一致",
        )

    playable_ids = frozenset(
        character.id for character in package.characters if character.is_playable
    )
    if len(playable_ids) < policy.max_players:
        raise PackageArchiveError(
            "PACKAGE_MULTIPLAYER_PLAYER_COUNT_INVALID",
            "可玩角色数量不能少于 multiplayer.max_players",
        )

    material_ids = _disjoint_material_ids(package)
    chapters_by_id = {chapter.id: chapter for chapter in package.chapters}
    for stage_record in package.stages:
        stage = _multiplayer_stage(stage_record.definition)
        chapter_character_ids = frozenset(stage.chapters)
        if chapter_character_ids != playable_ids:
            missing = sorted(playable_ids.difference(chapter_character_ids))
            non_playable = sorted(chapter_character_ids.difference(playable_ids))
            raise PackageArchiveError(
                "PACKAGE_REFERENCE_INVALID",
                f"stage {stage.id} chapters 必须恰好覆盖全部可玩角色; "
                f"缺少={missing}, 非可玩={non_playable}",
            )
        for character_id, chapter_id in stage.chapters.items():
            chapter = chapters_by_id.get(chapter_id)
            if chapter is None:
                raise PackageArchiveError(
                    "PACKAGE_REFERENCE_INVALID",
                    f"stage {stage.id} 的角色 {character_id} 指向不存在的章节: {chapter_id}",
                )
            if chapter.character_id != character_id:
                raise PackageArchiveError(
                    "PACKAGE_REFERENCE_INVALID",
                    f"stage {stage.id} 的章节 {chapter_id} 不属于角色 {character_id}",
                )
        for material in stage.public_materials:
            ensure_reference(
                f"stage {stage.id} 的公共材料引用",
                material.id,
                material_ids,
            )
        _validate_outcome_triggers(stage)


@dataclass(frozen=True, slots=True)
class MultiplayerPackagePolicy:
    """The validated package policy supported by the two-player MP-2 runtime."""

    min_players: Literal[2]
    max_players: Literal[2]
    character_assignment: Literal["required"]
    start_policy: Literal["all_players_ready"]
    duplicate_characters: Literal[False]
    playable_character_ids: tuple[str, ...]


def multiplayer_policy_from_package(package: ScriptPackageImport) -> MultiplayerPackagePolicy:
    """Validate exact two-player policy while reusing manifest player-count semantics."""

    config = package.package.config
    manifest_config = dict(config)
    manifest_config.pop("stage_index", None)
    raw_policy = manifest_config.pop("multiplayer", None)
    try:
        manifest = PackageManifest.model_validate(manifest_config)
    except ValidationError as error:
        raise PackageMultiplayerError("package.config") from error

    if manifest.info.min_players != 2:
        raise PackageMultiplayerError("info.min_players")
    if manifest.info.max_players != 2:
        raise PackageMultiplayerError("info.max_players")
    if not isinstance(raw_policy, dict):
        raise PackageMultiplayerError("multiplayer")
    policy = cast(dict[object, object], raw_policy)
    expected_fields = {
        "min_players",
        "max_players",
        "character_assignment",
        "start_policy",
        "duplicate_characters",
    }
    if any(not isinstance(key, str) for key in policy) or set(policy) != expected_fields:
        raise PackageMultiplayerError("multiplayer")
    _require_exact(policy, "min_players", 2)
    _require_exact(policy, "max_players", 2)
    _require_exact(policy, "character_assignment", "required")
    _require_exact(policy, "start_policy", "all_players_ready")
    _require_exact(policy, "duplicate_characters", False)

    playable = tuple(
        character.id
        for character in sorted(package.characters, key=lambda item: (item.sort_order, item.id))
        if character.is_playable
    )
    if len(playable) < 2 or len(set(playable)) != len(playable):
        raise PackageMultiplayerError("characters.playable")
    return MultiplayerPackagePolicy(
        min_players=2,
        max_players=2,
        character_assignment="required",
        start_policy="all_players_ready",
        duplicate_characters=False,
        playable_character_ids=playable,
    )


@dataclass(frozen=True, slots=True)
class MultiplayerPlayabilityDiagnostic:
    """Stable package-level reason why a room cannot use a multiplayer package."""

    code: str
    message: str
    field: str
    stage_id: str | None = None
    outcome_id: str | None = None
    ending_id: str | None = None

    def details(self) -> dict[str, str | None]:
        return {
            "diagnostic_code": self.code,
            "field": self.field,
            "stage_id": self.stage_id,
            "outcome_id": self.outcome_id,
            "ending_id": self.ending_id,
        }


@dataclass(frozen=True, slots=True)
class MultiplayerEndingResolution:
    """One authored final-judgment outcome resolved to an existing ending."""

    outcome_id: str
    ending_id: str


@dataclass(frozen=True, slots=True)
class MultiplayerPackagePlayability:
    """Immutable decision shared by import, publication, room start, and snapshots."""

    playable: bool
    diagnostics: tuple[MultiplayerPlayabilityDiagnostic, ...]
    policy: MultiplayerPackagePolicy | None
    terminal_stage_id: str | None
    ending_resolutions: tuple[MultiplayerEndingResolution, ...]


def multiplayer_package_playability(
    package: ScriptPackageImport,
) -> MultiplayerPackagePlayability:
    """Return the deterministic Multiplayer v1 playability decision for one package."""

    try:
        policy = multiplayer_policy_from_package(package)
    except PackageMultiplayerError as error:
        if error.field.startswith("info."):
            code = "PACKAGE_MULTIPLAYER_PLAYER_RANGE_INVALID"
            message = "package.yml info 与 multiplayer 的 min_players/max_players 必须一致"
        elif error.field == "characters.playable":
            code = "PACKAGE_MULTIPLAYER_PLAYER_COUNT_INVALID"
            message = "可玩角色数量不能少于 multiplayer.max_players"
        else:
            code = "PACKAGE_MULTIPLAYER_POLICY_INVALID"
            message = "剧本包不满足双人 Multiplayer v1 运行策略"
        diagnostic = MultiplayerPlayabilityDiagnostic(
            code=code,
            message=message,
            field=error.field,
        )
        return MultiplayerPackagePlayability(False, (diagnostic,), None, None, ())

    try:
        manifest_config = dict(package.package.config)
        manifest_config.pop("stage_index", None)
        manifest = PackageManifest.model_validate_json(
            json.dumps(manifest_config, ensure_ascii=False)
        )
        _validate_multiplayer_content(package, manifest)
        ordered_stages = multiplayer_stages_from_package(package)
        stage_contracts = tuple(_multiplayer_stage(stage.definition) for stage in ordered_stages)
    except PackageArchiveError as error:
        diagnostic = MultiplayerPlayabilityDiagnostic(
            code=error.code,
            message=error.message,
            field="package",
        )
        return MultiplayerPackagePlayability(False, (diagnostic,), policy, None, ())
    except (PackageMultiplayerError, ValidationError) as error:
        field = error.field if isinstance(error, PackageMultiplayerError) else "stages"
        diagnostic = MultiplayerPlayabilityDiagnostic(
            code="PACKAGE_MULTIPLAYER_STAGE_INVALID",
            message="多人阶段定义无法形成可运行契约",
            field=field,
        )
        return MultiplayerPackagePlayability(False, (diagnostic,), policy, None, ())

    diagnostics: list[MultiplayerPlayabilityDiagnostic] = []
    final_stages: list[tuple[MultiplayerStageDefinition, FinalJudgmentSettlementDefinition]] = []
    for stage in stage_contracts:
        settlement = stage.settlement
        if isinstance(settlement, FinalJudgmentSettlementDefinition):
            final_stages.append((stage, settlement))
    if len(final_stages) != 1 or final_stages[0][0].id != stage_contracts[-1].id:
        stage_id = final_stages[0][0].id if final_stages else None
        diagnostics.append(
            MultiplayerPlayabilityDiagnostic(
                code="PACKAGE_MULTIPLAYER_TERMINAL_STAGE_INVALID",
                message="多人剧本必须且只能以一个 final_judgment 阶段结束",
                field="stages",
                stage_id=stage_id,
            )
        )
        return MultiplayerPackagePlayability(False, tuple(diagnostics), policy, None, ())

    for stage in stage_contracts[:-1]:
        if stage.settlement.default_effect is SettlementEffect.RECORD_AND_CONTINUE:
            continue
        diagnostics.append(
            MultiplayerPlayabilityDiagnostic(
                code="PACKAGE_MULTIPLAYER_STAGE_EFFECT_UNSUPPORTED",
                message="非终局阶段只支持 record_and_continue 效果",
                field=f"stages.{stage.id}.settlement.default_effect",
                stage_id=stage.id,
            )
        )

    terminal_stage, settlement = final_stages[0]
    if settlement.default_effect is not SettlementEffect.BRANCH:
        diagnostics.append(
            MultiplayerPlayabilityDiagnostic(
                code="PACKAGE_MULTIPLAYER_TERMINAL_EFFECT_UNSUPPORTED",
                message="最终判断必须使用 branch 终局效果",
                field=f"stages.{terminal_stage.id}.settlement.default_effect",
                stage_id=terminal_stage.id,
            )
        )

    declared_outcomes = tuple(option.outcome_id for option in settlement.options)
    if settlement.tie_outcome_id is not None:
        declared_outcomes = (*declared_outcomes, settlement.tie_outcome_id)
    declared_outcome_set = frozenset(declared_outcomes)
    ending_ids = frozenset(ending.id for ending in package.endings)
    resolutions: list[MultiplayerEndingResolution] = []
    for outcome_id in declared_outcomes:
        ending_id = settlement.ending_by_outcome.get(outcome_id)
        field = f"stages.{terminal_stage.id}.settlement.ending_by_outcome.{outcome_id}"
        if ending_id is None:
            diagnostics.append(
                MultiplayerPlayabilityDiagnostic(
                    code="PACKAGE_MULTIPLAYER_ENDING_MAPPING_MISSING",
                    message=f"最终判断结果缺少结局映射: {outcome_id}",
                    field=field,
                    stage_id=terminal_stage.id,
                    outcome_id=outcome_id,
                )
            )
        elif ending_id not in ending_ids:
            diagnostics.append(
                MultiplayerPlayabilityDiagnostic(
                    code="PACKAGE_MULTIPLAYER_ENDING_REFERENCE_INVALID",
                    message=f"最终判断映射指向不存在的结局: {ending_id}",
                    field=field,
                    stage_id=terminal_stage.id,
                    outcome_id=outcome_id,
                    ending_id=ending_id,
                )
            )
        else:
            resolutions.append(
                MultiplayerEndingResolution(outcome_id=outcome_id, ending_id=ending_id)
            )
    for outcome_id in sorted(settlement.ending_by_outcome.keys() - declared_outcome_set):
        diagnostics.append(
            MultiplayerPlayabilityDiagnostic(
                code="PACKAGE_MULTIPLAYER_ENDING_MAPPING_OUTCOME_INVALID",
                message=f"结局映射包含未声明的最终判断结果: {outcome_id}",
                field=f"stages.{terminal_stage.id}.settlement.ending_by_outcome.{outcome_id}",
                stage_id=terminal_stage.id,
                outcome_id=outcome_id,
                ending_id=settlement.ending_by_outcome[outcome_id],
            )
        )

    return MultiplayerPackagePlayability(
        playable=not diagnostics,
        diagnostics=tuple(diagnostics),
        policy=policy,
        terminal_stage_id=terminal_stage.id,
        ending_resolutions=tuple(resolutions),
    )


def multiplayer_stages_from_package(package: ScriptPackageImport) -> tuple[StageRecord, ...]:
    """Return stages in canonical authored order after checking index/record agreement."""

    try:
        stage_index = stage_index_from_mapping(package.stage_index)
    except (PackageArchiveError, ValidationError) as error:
        raise PackageMultiplayerError("stage_index") from error

    records: dict[str, StageRecord] = {}
    for record in package.stages:
        if record.id in records:
            raise PackageMultiplayerError(f"stage.{record.id}.duplicate")
        records[record.id] = record

    index_ids = {item.id for item in stage_index.stages}
    if set(records) != index_ids:
        raise PackageMultiplayerError("stage_index.membership")

    ordered: list[StageRecord] = []
    for item in sorted(stage_index.stages, key=lambda value: (value.sort_order, value.id)):
        record = records[item.id]
        if record.name != item.name:
            raise PackageMultiplayerError(f"stage.{item.id}.name")
        if record.sort_order != item.sort_order:
            raise PackageMultiplayerError(f"stage.{item.id}.sort_order")
        ordered.append(record)
    if not ordered:
        raise PackageMultiplayerError("stage_index.stages")
    return tuple(ordered)


def first_multiplayer_stage_from_package(package: ScriptPackageImport) -> StageRecord:
    """Return the first stage by authoritative ``sort_order`` then ID."""

    return multiplayer_stages_from_package(package)[0]


def multiplayer_stage_from_package(package: ScriptPackageImport, stage_id: str) -> StageRecord:
    """Extract one validated authoritative stage by ID."""

    for stage in multiplayer_stages_from_package(package):
        if stage.id == stage_id:
            return stage
    raise PackageMultiplayerError(f"stage.{stage_id}")


def multiplayer_stage_contract(
    package: ScriptPackageImport,
    stage_id: str,
) -> MultiplayerStageDefinition:
    """Return one validated stage as the standalone multiplayer contract."""

    return _multiplayer_stage(multiplayer_stage_from_package(package, stage_id).definition)


def multiplayer_stage_definition(package: ScriptPackageImport, stage_id: str) -> JsonMapping:
    """Return a defensive copy of one validated stage's runtime definition."""

    return deepcopy(multiplayer_stage_from_package(package, stage_id).definition)


def _multiplayer_stage(definition: JsonMapping) -> MultiplayerStageDefinition:
    selected: JsonMapping = {"id": definition.get("id")}
    for key in MULTIPLAYER_STAGE_KEYS:
        selected[key] = definition.get(key)
    return MULTIPLAYER_STAGE_ADAPTER.validate_json(json.dumps(selected, ensure_ascii=False))


def _disjoint_material_ids(package: ScriptPackageImport) -> frozenset[str]:
    namespaces = (
        ("clue", (clue.id for clue in package.clues)),
        ("evidence", (evidence.id for evidence in package.evidences)),
        ("media", (media.id for media in package.media_assets)),
    )
    owners: dict[str, str] = {}
    for namespace, values in namespaces:
        for material_id in values:
            previous = owners.get(material_id)
            if previous is not None:
                raise PackageArchiveError(
                    "PACKAGE_DUPLICATE_ID",
                    f"公共材料 id 跨 {previous}/{namespace} 命名空间重复: {material_id}",
                )
            owners[material_id] = namespace
    return frozenset(owners)


def _validate_outcome_triggers(stage: MultiplayerStageDefinition) -> None:
    settlement = stage.settlement
    declared_outcomes: set[str] = set()
    if isinstance(
        settlement,
        SecretVoteSettlementDefinition
        | SharedChoiceSettlementDefinition
        | FinalJudgmentSettlementDefinition,
    ):
        declared_outcomes.update(option.outcome_id for option in settlement.options)
    if isinstance(settlement, SecretVoteSettlementDefinition):
        declared_outcomes.add(settlement.tie_outcome_id)
    elif (
        isinstance(settlement, FinalJudgmentSettlementDefinition)
        and settlement.tie_outcome_id is not None
    ):
        declared_outcomes.add(settlement.tie_outcome_id)

    for material in stage.public_materials:
        if not material.reveal_at.startswith("outcome:"):
            continue
        outcome_id = material.reveal_at.removeprefix("outcome:")
        ensure_reference(
            f"stage {stage.id} 的公共材料 outcome trigger",
            outcome_id,
            frozenset(declared_outcomes),
        )


def _require_exact(policy: dict[object, object], key: str, expected: object) -> None:
    value = policy[key]
    if type(value) is not type(expected) or value != expected:
        raise PackageMultiplayerError(f"multiplayer.{key}")


class PackageMultiplayerError(ValueError):
    """Report package data that cannot satisfy the MP-2 multiplayer contract."""

    def __init__(self, field: str) -> None:
        super().__init__(f"invalid two-player package field: {field}")
        self.field = field
