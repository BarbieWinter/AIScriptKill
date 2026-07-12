"""定义并校验权威的幕与阶段索引。"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from engine.core.package_archive import PackageArchiveError
from engine.core.package_schema import JsonMapping


class StageIndexModel(BaseModel):
    """对阶段索引模型应用严格的不可变校验。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
    )


class StageIndexItem(StageIndexModel):
    """声明一个阶段及其权威执行顺序。"""

    id: str = Field(description="stages/_index.yml stages[].id")
    name: str = Field(description="stages/_index.yml stages[].name")
    sort_order: int = Field(description="stages/_index.yml stages[].sort_order")
    meta: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="stages/_index.yml stages[].meta",
    )


class StageActItem(StageIndexModel):
    """声明一幕及其有序成员阶段。"""

    id: str = Field(description="stages/_index.yml acts[].id")
    name: str = Field(description="stages/_index.yml acts[].name")
    stages: list[str] = Field(
        default_factory=list,
        description="stages/_index.yml acts[].stages",
    )


class StageIndexDefinition(StageIndexModel):
    """建模完整且权威的 stages/_index.yml 文件。"""

    stages: list[StageIndexItem] = Field(
        default_factory=list,
        description="stages/_index.yml stages",
    )
    acts: list[StageActItem] = Field(
        default_factory=list,
        description="stages/_index.yml acts",
    )


def stage_index_from_mapping(raw: JsonMapping) -> StageIndexDefinition:
    """解析阶段索引，并拒绝空项、重复项或悬空项。"""

    stage_index = StageIndexDefinition.model_validate(raw)
    _ensure_stage_index_has_stages(stage_index)
    _ensure_unique_stage_index_ids(stage_index)
    _ensure_act_stage_references(stage_index)
    return stage_index


def stage_index_items_by_id(
    stage_index: StageIndexDefinition,
) -> dict[str, StageIndexItem]:
    """按标识符索引权威阶段条目。"""

    return {item.id: item for item in stage_index.stages}


def ordered_stage_index_items(
    stage_index: StageIndexDefinition,
) -> tuple[StageIndexItem, ...]:
    """返回按 sort_order 排序的权威阶段条目。"""

    return tuple(sorted(stage_index.stages, key=lambda item: item.sort_order))


def stage_act_ids_by_stage(stage_index: StageIndexDefinition) -> dict[str, str]:
    """将每个阶段映射到唯一所属幕，并拒绝重复归属。"""

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
