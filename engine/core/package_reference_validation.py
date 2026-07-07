from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import ActionType, JsonValue
from engine.core.package_archive import PackageArchiveError
from engine.core.package_event_validation import validate_events
from engine.core.package_schema import ScriptPackageImport, StageRecord
from engine.core.package_validation_context import (
    ACTION_TYPES,
    SUPPORTED_CONDITION_TYPES,
    PackageValidationContext,
    ensure_reference,
    json_mapping_list,
    metadata_text,
    metadata_texts,
    required_mapping,
    required_text,
)
from engine.core.package_yaml import (
    CharacterDefinition,
    EvidenceDefinition,
    SceneDefinition,
)


class StageReferences(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    available_actions: list[ActionType] = Field(default_factory=list)
    available_characters: list[str] = Field(default_factory=list)
    available_scenes: list[str] = Field(default_factory=list)
    available_clue_rounds: list[str] = Field(default_factory=list)


def validate_stage_references(
    stages: tuple[StageRecord, ...],
    context: PackageValidationContext,
) -> None:
    for stage in stages:
        references = StageReferences.model_validate(stage.definition)
        for character_id in references.available_characters:
            ensure_reference(f"stage {stage.id} 的角色引用", character_id, context.character_ids)
        for scene_id in references.available_scenes:
            ensure_reference(f"stage {stage.id} 的场景引用", scene_id, context.scene_ids)
        for round_id in references.available_clue_rounds:
            ensure_reference(f"stage {stage.id} 的线索轮次引用", round_id, context.clue_round_ids)
        _validate_stage_conditions(stage, context)


def validate_character_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    for character in package.characters:
        definition = CharacterDefinition.model_validate(character.definition)
        for reaction in definition.evidence_reactions:
            ensure_reference(
                f"character {character.id} 的证物反应引用",
                reaction.evidence_id,
                context.evidence_ids,
            )
            if reaction.stage_visible is not None:
                ensure_reference(
                    f"character {character.id} 的证物反应阶段引用",
                    reaction.stage_visible,
                    context.stage_ids,
                )


def validate_scene_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    for scene in package.scenes:
        definition = SceneDefinition.model_validate(scene.definition)
        for stage_id in definition.available_in_stages:
            ensure_reference(f"scene {scene.id} 的阶段引用", stage_id, context.stage_ids)
        for hotspot in json_mapping_list(scene.definition.get("hotspots")):
            validate_events(
                f"scene {scene.id} hotspot",
                json_mapping_list(hotspot.get("on_click")),
                context,
            )


def validate_clue_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    for clue in package.clues:
        stage_id = metadata_text(clue.metadata.get("stage_visible"))
        if stage_id is not None:
            ensure_reference(f"clue {clue.id} 的阶段引用", stage_id, context.stage_ids)
        scene_id = metadata_text(clue.metadata.get("related_scene"))
        if scene_id is not None:
            ensure_reference(f"clue {clue.id} 的场景引用", scene_id, context.scene_ids)
        for character_id in metadata_texts(clue.metadata.get("related_characters")):
            ensure_reference(f"clue {clue.id} 的角色引用", character_id, context.character_ids)


def validate_evidence_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    for evidence in package.evidences:
        definition = EvidenceDefinition.model_validate(evidence.metadata)
        ensure_reference(
            f"evidence {evidence.id} 的发现场景引用",
            definition.discovery.scene_id,
            context.scene_ids,
        )
        if definition.discovery.stage_visible is not None:
            ensure_reference(
                f"evidence {evidence.id} 的发现阶段引用",
                definition.discovery.stage_visible,
                context.stage_ids,
            )
        for reaction in definition.npc_reactions:
            ensure_reference(
                f"evidence {evidence.id} 的 NPC 反应引用",
                reaction.character_id,
                context.character_ids,
            )


def validate_ending_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    for ending in package.endings:
        validate_condition(f"ending {ending.id} condition", ending.condition, context)
        validate_events(f"ending {ending.id} on_trigger", ending.on_trigger, context)


def validate_condition(
    owner: str,
    condition: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    condition_type = required_text(owner, condition, "type")
    if condition_type not in SUPPORTED_CONDITION_TYPES:
        raise PackageArchiveError(
            "PACKAGE_CONDITION_TYPE_INVALID",
            f"{owner} 使用了不支持的条件类型: {condition_type}",
        )
    _validate_condition_references(owner, condition_type, condition, context)


def _validate_stage_conditions(stage: StageRecord, context: PackageValidationContext) -> None:
    _validate_conditions(
        f"stage {stage.id} entry_conditions",
        json_mapping_list(stage.definition.get("entry_conditions")),
        context,
    )
    _validate_conditions(
        f"stage {stage.id} exit_conditions",
        json_mapping_list(stage.definition.get("exit_conditions")),
        context,
    )
    validate_events(
        f"stage {stage.id} on_stage_entry",
        json_mapping_list(stage.definition.get("on_stage_entry")),
        context,
    )
    validate_events(
        f"stage {stage.id} on_stage_exit",
        json_mapping_list(stage.definition.get("on_stage_exit")),
        context,
    )
    for trigger in json_mapping_list(stage.definition.get("media_triggers")):
        validate_events(
            f"stage {stage.id} media_triggers",
            json_mapping_list(trigger.get("then")),
            context,
        )


def _validate_conditions(
    owner: str,
    conditions: list[dict[str, JsonValue]],
    context: PackageValidationContext,
) -> None:
    for condition in conditions:
        validate_condition(owner, condition, context)


def _validate_condition_references(
    owner: str,
    condition_type: str,
    condition: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    match condition_type:
        case "all" | "any":
            _validate_conditions(owner, json_mapping_list(condition.get("conditions")), context)
        case "not":
            validate_condition(owner, required_mapping(owner, condition, "condition"), context)
        case "stage_completed" | "stage_reached":
            ensure_reference(owner, required_text(owner, condition, "stage_id"), context.stage_ids)
        case "clues_discovered":
            _validate_clues_discovered_condition(owner, condition, context)
        case "clue_discovered":
            ensure_reference(owner, required_text(owner, condition, "clue_id"), context.clue_ids)
        case "evidence_found":
            ensure_reference(
                owner,
                required_text(owner, condition, "evidence_id"),
                context.evidence_ids,
            )
        case "evidence_shown_to_npc":
            _validate_evidence_shown_condition(owner, condition, context)
        case "character_talked_to" | "npc_state_reached":
            ensure_reference(
                owner,
                required_text(owner, condition, "character_id"),
                context.character_ids,
            )
        case "player_action_performed":
            ensure_reference(owner, required_text(owner, condition, "action"), ACTION_TYPES)
        case _:
            return


def _validate_clues_discovered_condition(
    owner: str,
    condition: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    round_id = metadata_text(condition.get("in_round"))
    if round_id is not None:
        ensure_reference(owner, round_id, context.clue_round_ids)
    scene_id = metadata_text(condition.get("in_scene"))
    if scene_id is not None:
        ensure_reference(owner, scene_id, context.scene_ids)


def _validate_evidence_shown_condition(
    owner: str,
    condition: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    ensure_reference(owner, required_text(owner, condition, "evidence_id"), context.evidence_ids)
    ensure_reference(owner, required_text(owner, condition, "character_id"), context.character_ids)
