"""定义并加载严格的 DM 指引剧本包契约。"""

import re
from collections.abc import Mapping
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.api.schemas.common import JsonValue
from engine.core.package_asset_validation import validate_asset_path_reference
from engine.core.package_schema import ScriptPackageImport
from engine.core.package_validation_context import PackageValidationContext, ensure_reference

_EVIDENCE_CHAIN_SEPARATOR = re.compile(r"\s*(?:->|→)\s*")
_EVIDENCE_CHAIN_TERMINALS = frozenset(("culprit",))


class DmGuideModel(BaseModel):
    """应用 DM 指引模型共享的严格不可变策略。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )


class DmGuideTimelineEntry(DmGuideModel):
    """记录隐藏案件真相中的一项时序事实。"""

    time: str = Field(description="dm_guide/truth.yml truth.timeline[].time")
    event: str = Field(description="dm_guide/truth.yml truth.timeline[].event")
    hidden: bool = Field(default=False, description="dm_guide/truth.yml truth.timeline[].hidden")


class DmGuideAlternativeEnding(DmGuideModel):
    """描述一个可选的真相驱动替代结局。"""

    id: str = Field(description="dm_guide/truth.yml truth.alternative_endings[].id")
    condition: str = Field(description="dm_guide/truth.yml truth.alternative_endings[].condition")
    news_broadcast: str | None = Field(
        default=None,
        description="dm_guide/truth.yml truth.alternative_endings[].news_broadcast",
    )


class DmGuideTruth(DmGuideModel):
    """记录仅 DM 可用的权威案件真相。"""

    case_summary: str | None = Field(
        default=None,
        description="dm_guide/truth.yml truth.case_summary",
    )
    murderer: str | None = Field(default=None, description="dm_guide/truth.yml truth.murderer")
    victim: str | None = Field(default=None, description="dm_guide/truth.yml truth.victim")
    motive: str | None = Field(default=None, description="dm_guide/truth.yml truth.motive")
    timeline: list[DmGuideTimelineEntry] = Field(
        default_factory=list,
        description="dm_guide/truth.yml truth.timeline",
    )
    key_evidence_chain: list[str] = Field(
        default_factory=list,
        description="dm_guide/truth.yml truth.key_evidence_chain",
    )
    alternative_endings: list[DmGuideAlternativeEnding] = Field(
        default_factory=list,
        description="dm_guide/truth.yml truth.alternative_endings",
    )


class DmGuideTruthFile(DmGuideModel):
    """建模可选真相指引文件的根节点。"""

    truth: DmGuideTruth = Field(description="dm_guide/truth.yml truth")


class DmGuideKeyMoment(DmGuideModel):
    """将玩家动作与所需的 DM 响应配对。"""

    action: str = Field(description="dm_guide/stage_notes.yml key_moments[].action")
    dm_action: str = Field(description="dm_guide/stage_notes.yml key_moments[].dm_action")


class DmGuideStageNote(DmGuideModel):
    """描述一个阶段中的 DM 私有行为和提示。"""

    stage_id: str = Field(description="dm_guide/stage_notes.yml stage_notes[].stage_id")
    dm_behavior: str = Field(description="dm_guide/stage_notes.yml stage_notes[].dm_behavior")
    notes: str = Field(description="dm_guide/stage_notes.yml stage_notes[].notes")
    atmosphere: str | None = Field(
        default=None,
        description="dm_guide/stage_notes.yml stage_notes[].atmosphere",
    )
    key_moments: list[DmGuideKeyMoment] = Field(
        default_factory=list,
        description="dm_guide/stage_notes.yml stage_notes[].key_moments",
    )
    prop_usage: list[str] = Field(
        default_factory=list,
        description="dm_guide/stage_notes.yml stage_notes[].prop_usage",
    )
    trap_mechanics: list[str] = Field(
        default_factory=list,
        description="dm_guide/stage_notes.yml stage_notes[].trap_mechanics",
    )


class DmGuideStageNotesFile(DmGuideModel):
    """建模可选阶段注释指引文件的根节点。"""

    stage_notes: list[DmGuideStageNote] = Field(
        description="dm_guide/stage_notes.yml stage_notes",
    )


class DmGuidePerformancePhase(DmGuideModel):
    """描述一个演出阶段的演员指导。"""

    character: str = Field(description="dm_guide/performance_guide.yml phase character")
    actor: str = Field(description="dm_guide/performance_guide.yml phase actor")
    traits: list[str] = Field(
        default_factory=list,
        description="dm_guide/performance_guide.yml phase traits",
    )
    pre_broadcast: str | None = Field(
        default=None,
        description="dm_guide/performance_guide.yml phase pre_broadcast",
    )
    post_broadcast: str | None = Field(
        default=None,
        description="dm_guide/performance_guide.yml phase post_broadcast",
    )


class DmGuideDialogueLine(DmGuideModel):
    """记录一句特定演出阶段的剧本台词。"""

    phase: str = Field(description="dm_guide/performance_guide.yml key_dialogue_lines[].phase")
    line: str = Field(description="dm_guide/performance_guide.yml key_dialogue_lines[].line")
    emotion: str = Field(description="dm_guide/performance_guide.yml key_dialogue_lines[].emotion")


class DmGuidePerformance(DmGuideModel):
    """编组私有演出阶段和关键对话台词。"""

    dm_split_personality: dict[str, DmGuidePerformancePhase] = Field(
        default_factory=dict,
        description="dm_guide/performance_guide.yml performance.dm_split_personality",
    )
    key_dialogue_lines: list[DmGuideDialogueLine] = Field(
        default_factory=list,
        description="dm_guide/performance_guide.yml performance.key_dialogue_lines",
    )


class DmGuidePerformanceFile(DmGuideModel):
    """建模可选演出指引文件的根节点。"""

    performance: DmGuidePerformance = Field(
        description="dm_guide/performance_guide.yml performance",
    )


class DmGuideFiles(DmGuideModel):
    """汇总全部可选的类型化 DM 指引文档。"""

    truth: DmGuideTruthFile | None = Field(default=None, description="dm_guide/truth.yml")
    stage_notes: DmGuideStageNotesFile | None = Field(
        default=None,
        description="dm_guide/stage_notes.yml",
    )
    performance_guide: DmGuidePerformanceFile | None = Field(
        default=None,
        description="dm_guide/performance_guide.yml",
    )


def validate_dm_guide(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    """校验 DM 指引引用及其引用的媒体资源。"""

    guide = DmGuideFiles.model_validate(package.dm_guide)
    if guide.stage_notes is not None:
        for note in guide.stage_notes.stage_notes:
            ensure_reference("dm_guide.stage_notes stage_id", note.stage_id, context.stage_ids)
    if guide.performance_guide is not None:
        for dialogue_line in guide.performance_guide.performance.key_dialogue_lines:
            ensure_reference(
                "dm_guide.performance key_dialogue_lines phase",
                dialogue_line.phase,
                context.stage_ids,
            )
    if guide.truth is not None:
        truth = guide.truth.truth
        if truth.murderer is not None:
            ensure_reference("dm_guide.truth murderer", truth.murderer, context.character_ids)
        if truth.victim is not None:
            ensure_reference("dm_guide.truth victim", truth.victim, context.character_ids)
        _validate_key_evidence_chains(truth.key_evidence_chain, context)
        for ending in truth.alternative_endings:
            validate_asset_path_reference(
                f"dm_guide.truth alternative ending {ending.id} news_broadcast",
                ending.news_broadcast,
                context,
            )


def dm_guide_chain_ids(dm_guide: Mapping[str, JsonValue]) -> frozenset[str]:
    """返回真相文件声明的推理链 ID；旧版列表统一对应 `main`。"""

    guide = DmGuideFiles.model_validate(dm_guide)
    if guide.truth is None:
        return frozenset()
    chains = guide.truth.truth.key_evidence_chain
    if len(chains) > 0:
        return frozenset(("main",))
    return frozenset()


def _validate_key_evidence_chains(
    chains: list[str],
    context: PackageValidationContext,
) -> None:
    for expression in chains:
        for evidence_id in _EVIDENCE_CHAIN_SEPARATOR.split(expression):
            if evidence_id in _EVIDENCE_CHAIN_TERMINALS:
                continue
            ensure_reference(
                "dm_guide.truth key_evidence_chain",
                evidence_id,
                context.evidence_ids,
            )
