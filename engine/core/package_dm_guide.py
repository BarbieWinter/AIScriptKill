from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.core.package_asset_validation import validate_asset_path_reference
from engine.core.package_schema import JsonMapping, ScriptPackageImport
from engine.core.package_validation_context import PackageValidationContext, ensure_reference


class DmGuideModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")


class DmGuideAlternativeEnding(DmGuideModel):
    id: str
    condition: str | None = None
    news_broadcast: str | None = None


class DmGuideTruth(DmGuideModel):
    alternative_endings: list[DmGuideAlternativeEnding] = Field(default_factory=list)


class DmGuideTruthFile(DmGuideModel):
    truth: DmGuideTruth = Field(default_factory=DmGuideTruth)


class DmGuideStageNote(DmGuideModel):
    stage_id: str


class DmGuideStageNotesFile(DmGuideModel):
    stage_notes: list[DmGuideStageNote] = Field(default_factory=list)


def validate_dm_guide(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> None:
    _validate_stage_notes(package.dm_guide, context)
    _validate_truth_assets(package.dm_guide, context)


def _validate_stage_notes(
    dm_guide: JsonMapping,
    context: PackageValidationContext,
) -> None:
    raw = _dm_guide_file(dm_guide, "stage_notes")
    if raw is None:
        return
    stage_notes = DmGuideStageNotesFile.model_validate(raw)
    for note in stage_notes.stage_notes:
        ensure_reference("dm_guide.stage_notes stage_id", note.stage_id, context.stage_ids)


def _validate_truth_assets(
    dm_guide: JsonMapping,
    context: PackageValidationContext,
) -> None:
    raw = _dm_guide_file(dm_guide, "truth")
    if raw is None:
        return
    truth_file = DmGuideTruthFile.model_validate(raw)
    for ending in truth_file.truth.alternative_endings:
        validate_asset_path_reference(
            f"dm_guide.truth alternative ending {ending.id} news_broadcast",
            ending.news_broadcast,
            context,
        )


def _dm_guide_file(dm_guide: JsonMapping, key: str) -> JsonMapping | None:
    value = dm_guide.get(key)
    if isinstance(value, dict):
        return value
    return None
