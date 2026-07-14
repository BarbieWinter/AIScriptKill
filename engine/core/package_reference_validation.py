"""校验跨剧本包文件和阶段定义的引用。"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import ActionType, JsonValue
from engine.core.condition_models import (
    ConditionDslError,
    ConditionNode,
    ConditionType,
    parse_condition,
)
from engine.core.package_archive import PackageArchiveError
from engine.core.package_asset_validation import knowledge_stage_id
from engine.core.package_event_validation import validate_events
from engine.core.package_schema import ScriptPackageImport, StageRecord
from engine.core.package_validation_context import (
    ACTION_TYPES,
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
    """解析跨文件引用校验使用的阶段所属 ID。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="ignore")

    available_actions: list[ActionType] = Field(
        default_factory=list,
        description="Actions enabled by this stage.",
    )
    available_characters: list[str] = Field(
        default_factory=list,
        description="Character IDs enabled by this stage.",
    )
    available_scenes: list[str] = Field(
        default_factory=list,
        description="Scene IDs enabled by this stage.",
    )
    available_clue_rounds: list[str] = Field(
        default_factory=list,
        description="Clue-round IDs enabled by this stage.",
    )


def validate_stage_references(
    stages: tuple[StageRecord, ...],
    context: PackageValidationContext,
) -> None:
    """校验阶段跳转、启用实体、条件和事件。"""

    for stage in stages:
        references = StageReferences.model_validate(stage.definition)
        for character_id in references.available_characters:
            ensure_reference(f"stage {stage.id} 的角色引用", character_id, context.character_ids)
        for scene_id in references.available_scenes:
            ensure_reference(f"stage {stage.id} 的场景引用", scene_id, context.scene_ids)
        for round_id in references.available_clue_rounds:
            ensure_reference(f"stage {stage.id} 的线索轮次引用", round_id, context.clue_round_ids)
        for target_stage in metadata_texts(stage.definition.get("allowed_transitions")):
            ensure_reference(
                f"stage {stage.id} 的显式跳转引用",
                target_stage,
                context.stage_ids,
            )
        _validate_stage_conditions(stage, context)


def validate_character_chapter_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    """校验人物章节所属角色和最早阶段引用。"""

    for chapter in package.chapters:
        ensure_reference(
            f"character chapter {chapter.id} 的角色引用",
            chapter.character_id,
            context.character_ids,
        )
        if chapter.stage_min is not None:
            ensure_reference(
                f"character chapter {chapter.id} 的最早阶段引用",
                chapter.stage_min,
                context.stage_ids,
            )
        release_type = metadata_text(chapter.release.get("type"))
        if release_type == "rule":
            rule_id = required_text(
                f"character chapter {chapter.id} 的授权规则",
                chapter.release,
                "rule_id",
            )
            if not _has_matching_chapter_unlock_event(package, chapter.id, rule_id):
                raise PackageArchiveError(
                    "PACKAGE_CHARACTER_CHAPTER_RELEASE_INVALID",
                    f"character chapter {chapter.id} 缺少同 rule_id 的授权事件: {rule_id}",
                )


def _has_matching_chapter_unlock_event(
    package: ScriptPackageImport,
    chapter_id: str,
    rule_id: str,
) -> bool:
    for event in _package_events(package):
        if (
            event.get("action") == "unlock_character_chapter"
            and event.get("chapter_id") == chapter_id
            and event.get("event_id") == rule_id
        ):
            return True
    return False


def _package_events(package: ScriptPackageImport) -> tuple[dict[str, JsonValue], ...]:
    events: list[dict[str, JsonValue]] = []
    for stage in package.stages:
        for field in ("on_stage_entry", "on_stage_exit"):
            events.extend(json_mapping_list(stage.definition.get(field)))
        for field in ("on_clue_discovered", "media_triggers"):
            for trigger in json_mapping_list(stage.definition.get(field)):
                events.extend(json_mapping_list(trigger.get("then")))
    for scene in package.scenes:
        for hotspot in json_mapping_list(scene.definition.get("hotspots")):
            events.extend(json_mapping_list(hotspot.get("on_click")))
    for ending in package.endings:
        events.extend(dict(event) for event in ending.on_trigger)
    return tuple(events)


def validate_character_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    """校验角色知识阶段、证物和反应条件。"""

    for character in package.characters:
        definition = CharacterDefinition.model_validate(character.definition)
        for stage_key in definition.knowledge:
            ensure_reference(
                f"character {character.id} 的知识阶段引用",
                knowledge_stage_id(stage_key),
                context.stage_ids,
            )
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
            if reaction.condition is not None:
                validate_condition(
                    f"character {character.id} 的证物反应条件",
                    reaction.condition,
                    context,
                )


def validate_scene_references(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    """校验场景阶段窗口和热点事件引用。"""

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
    """校验线索的阶段、场景和角色引用。"""

    for clue in package.clues:
        round_stage_id = metadata_text(clue.metadata.get("round_stage_visible"))
        if round_stage_id is not None:
            ensure_reference(
                f"clue round {clue.round_id} 的阶段引用",
                round_stage_id,
                context.stage_ids,
            )
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
    """校验证物发现和 NPC 反应引用。"""

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
    """校验结局条件和触发事件引用。"""

    for ending in package.endings:
        validate_condition(f"ending {ending.id} condition", ending.condition, context)
        validate_events(f"ending {ending.id} on_trigger", ending.on_trigger, context)


def validate_condition(
    owner: str,
    condition: dict[str, JsonValue],
    context: PackageValidationContext,
) -> None:
    """解析条件并校验其中引用的每个剧本包实体。"""

    try:
        node = parse_condition(condition)
    except ConditionDslError as exc:
        package_error_code = (
            "PACKAGE_CONDITION_TYPE_INVALID"
            if exc.code == "CONDITION_TYPE_INVALID"
            else "PACKAGE_CONDITION_INVALID"
        )
        raise PackageArchiveError(
            package_error_code,
            f"{owner} 条件不合法: {exc.message}",
        ) from exc
    _validate_condition_references(owner, node, context)


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
    for trigger in json_mapping_list(stage.definition.get("on_clue_discovered")):
        owner = f"stage {stage.id} on_clue_discovered"
        validate_condition(owner, required_mapping(owner, trigger, "condition"), context)
        then = trigger.get("then")
        if then is None:
            raise PackageArchiveError(
                "PACKAGE_MAPPING_LIST_INVALID",
                f"{owner}.then 必须是对象列表",
            )
        validate_events(owner, json_mapping_list(then), context)
    for trigger in json_mapping_list(stage.definition.get("media_triggers")):
        owner = f"stage {stage.id} media_triggers"
        ensure_reference(
            owner,
            required_text(owner, trigger, "clue_id"),
            context.clue_ids,
        )
        validate_events(owner, json_mapping_list(trigger.get("then")), context)


def _validate_conditions(
    owner: str,
    conditions: list[dict[str, JsonValue]],
    context: PackageValidationContext,
) -> None:
    for condition in conditions:
        validate_condition(owner, condition, context)


def _validate_condition_references(
    owner: str,
    condition: ConditionNode,
    context: PackageValidationContext,
) -> None:
    match condition.type:
        case ConditionType.ALL | ConditionType.ANY | ConditionType.COUNT:
            for child in condition.conditions:
                _validate_condition_references(owner, child, context)
        case ConditionType.NOT:
            if condition.condition is not None:
                _validate_condition_references(owner, condition.condition, context)
        case ConditionType.ALWAYS | ConditionType.NEVER:
            return
        case ConditionType.STAGE_COMPLETED | ConditionType.STAGE_REACHED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "stage_id"),
                context.stage_ids,
            )
        case ConditionType.ACT_COMPLETED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "act_id"),
                context.act_ids,
            )
        case ConditionType.CLUES_DISCOVERED:
            _validate_clues_discovered_condition(owner, condition.parameters, context)
        case ConditionType.CLUE_DISCOVERED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "clue_id"),
                context.clue_ids,
            )
        case ConditionType.EVIDENCE_FOUND | ConditionType.EVIDENCE_VIEWED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "evidence_id"),
                context.evidence_ids,
            )
        case ConditionType.CHARACTER_CHAPTER_READ:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "chapter_id"),
                context.chapter_ids,
            )
        case ConditionType.EVIDENCE_SHOWN_TO_NPC:
            _validate_evidence_shown_condition(owner, condition.parameters, context)
        case ConditionType.CHARACTER_TALKED_TO | ConditionType.NPC_STATE_REACHED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "character_id"),
                context.character_ids,
            )
        case ConditionType.PLAYER_ACTION_PERFORMED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "action_id"),
                ACTION_TYPES,
            )
        case ConditionType.PLAYER_USED_CARD:
            card_id = metadata_text(condition.parameters.get("card_id"))
            if card_id is not None:
                ensure_reference(owner, card_id, context.card_ids)
        case ConditionType.KEY_EVIDENCE_USED:
            for evidence_id in metadata_texts(condition.parameters.get("evidence_ids")):
                ensure_reference(owner, evidence_id, context.evidence_ids)
        case ConditionType.DEDUCTION_CHAIN_COMPLETE:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "chain_id"),
                context.deduction_chain_ids,
            )
        case ConditionType.EVENT_TRIGGERED | ConditionType.EVENT_NOT_TRIGGERED:
            ensure_reference(
                owner,
                required_text(owner, condition.parameters, "event_id"),
                context.event_ids,
            )
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
