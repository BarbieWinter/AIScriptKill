"""加载权威阶段索引及与其严格匹配的阶段文件。"""

from zipfile import ZipFile

from engine.core.package_archive import PackageArchiveError, read_yaml_mapping, yaml_paths
from engine.core.package_records import stage_record_from_mapping
from engine.core.package_schema import JsonMapping, StageRecord
from engine.core.package_stage_index import (
    StageIndexDefinition,
    ordered_stage_index_items,
    stage_act_ids_by_stage,
    stage_index_from_mapping,
)


def load_stage_index(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> JsonMapping:
    """加载必需的 stages/_index.yml 映射。"""

    path = f"{root}stages/_index.yml"
    if path not in names:
        raise PackageArchiveError(
            "PACKAGE_STAGE_INDEX_REQUIRED",
            "剧本包必须包含 stages/_index.yml",
        )
    return read_yaml_mapping(archive, path)


def load_stages(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
    stage_index_raw: JsonMapping,
) -> tuple[StageRecord, ...]:
    """校验索引与文件一致性，并按权威顺序返回阶段。"""

    stage_index = stage_index_from_mapping(stage_index_raw)
    act_ids = stage_act_ids_by_stage(stage_index)
    stage_mappings = _stage_mappings_by_id(archive, names, root)
    _ensure_stage_files_match_index(frozenset(stage_mappings), stage_index)
    return tuple(
        stage_record_from_mapping(stage_mappings[item.id], item, act_ids.get(item.id))
        for item in ordered_stage_index_items(stage_index)
    )


def _stage_mappings_by_id(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> dict[str, JsonMapping]:
    mappings: dict[str, JsonMapping] = {}
    for path in yaml_paths(names, root, "stages"):
        raw = read_yaml_mapping(archive, path)
        stage_id = str(raw.get("id", ""))
        if stage_id in mappings:
            raise PackageArchiveError("PACKAGE_DUPLICATE_ID", f"重复的 stage id: {stage_id}")
        mappings[stage_id] = raw
    if len(mappings) == 0:
        raise PackageArchiveError("PACKAGE_STAGES_REQUIRED", "剧本包至少需要一个 stage YAML")
    return mappings


def _ensure_stage_files_match_index(
    stage_file_ids: frozenset[str],
    stage_index: StageIndexDefinition,
) -> None:
    index_stage_ids = frozenset(stage.id for stage in stage_index.stages)
    for stage_id in sorted(index_stage_ids.difference(stage_file_ids)):
        raise PackageArchiveError(
            "PACKAGE_STAGE_INDEX_INVALID",
            f"stages/_index.yml 定义了缺失的 stage YAML: {stage_id}",
        )
    for stage_id in sorted(stage_file_ids.difference(index_stage_ids)):
        raise PackageArchiveError(
            "PACKAGE_STAGE_INDEX_INVALID",
            f"stage YAML 未在 stages/_index.yml 中声明: {stage_id}",
        )
