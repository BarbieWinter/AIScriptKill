from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.core.package_archive import PackageArchiveError
from engine.core.package_schema import JsonMapping


class StageIndexModel(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True, extra="allow")


class StageIndexItem(StageIndexModel):
    id: str
    name: str
    sort_order: int
    meta: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class StageActItem(StageIndexModel):
    id: str
    name: str
    stages: list[str] = Field(default_factory=list)


class StageIndexDefinition(StageIndexModel):
    stages: list[StageIndexItem] = Field(default_factory=list)
    acts: list[StageActItem] = Field(default_factory=list)


def stage_index_from_mapping(raw: JsonMapping) -> StageIndexDefinition:
    stage_index = StageIndexDefinition.model_validate(raw)
    _ensure_stage_index_has_stages(stage_index)
    _ensure_unique_stage_index_ids(stage_index)
    _ensure_act_stage_references(stage_index)
    return stage_index


def stage_index_items_by_id(
    stage_index: StageIndexDefinition,
) -> dict[str, StageIndexItem]:
    return {item.id: item for item in stage_index.stages}


def ordered_stage_index_items(
    stage_index: StageIndexDefinition,
) -> tuple[StageIndexItem, ...]:
    return tuple(sorted(stage_index.stages, key=lambda item: item.sort_order))


def stage_act_ids_by_stage(stage_index: StageIndexDefinition) -> dict[str, str]:
    act_ids: dict[str, str] = {}
    for act in stage_index.acts:
        for stage_id in act.stages:
            existing_act_id = act_ids.get(stage_id)
            if existing_act_id is not None:
                raise PackageArchiveError(
                    "PACKAGE_STAGE_INDEX_INVALID",
                    f"stage {stage_id} 同时属于多个 act: {existing_act_id}, {act.id}",
                )
            act_ids[stage_id] = act.id
    return act_ids


def _ensure_stage_index_has_stages(stage_index: StageIndexDefinition) -> None:
    if len(stage_index.stages) > 0:
        return
    raise PackageArchiveError("PACKAGE_STAGE_INDEX_REQUIRED", "stages/_index.yml 必须定义 stages")


def _ensure_unique_stage_index_ids(stage_index: StageIndexDefinition) -> None:
    stage_ids: set[str] = set()
    for stage in stage_index.stages:
        if stage.id in stage_ids:
            raise PackageArchiveError(
                "PACKAGE_DUPLICATE_ID",
                f"stages/_index.yml 中重复的 stage id: {stage.id}",
            )
        stage_ids.add(stage.id)
    act_ids: set[str] = set()
    for act in stage_index.acts:
        if act.id in act_ids:
            raise PackageArchiveError(
                "PACKAGE_DUPLICATE_ID",
                f"stages/_index.yml 中重复的 act id: {act.id}",
            )
        act_ids.add(act.id)


def _ensure_act_stage_references(stage_index: StageIndexDefinition) -> None:
    stage_ids = frozenset(stage.id for stage in stage_index.stages)
    for act in stage_index.acts:
        for stage_id in act.stages:
            if stage_id in stage_ids:
                continue
            raise PackageArchiveError(
                "PACKAGE_STAGE_INDEX_INVALID",
                f"act {act.id} 指向 stages/_index.yml 未定义的 stage: {stage_id}",
            )
