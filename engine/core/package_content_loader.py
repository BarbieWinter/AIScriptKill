"""从已校验归档加载并交叉检查类型化剧本包内容。"""

import mimetypes
from zipfile import ZipFile

from engine.core.package_archive import PackageArchiveError, read_yaml_mapping, yaml_paths
from engine.core.package_records import (
    character_record_from_mapping,
    clue_records_from_mapping,
    ending_records_from_mapping,
    evidence_record_from_mapping,
    media_records_from_mapping,
    scene_record_from_mapping,
)
from engine.core.package_schema import (
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    MediaRecord,
    PackageAssetRecord,
    SceneRecord,
)
from engine.core.package_yaml import CharacterIndex, CharacterIndexItem


def load_characters(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[CharacterRecord, ...]:
    """加载已索引角色文件，并要求索引与文件严格对应。"""

    index = _character_index(archive, root, names)
    records: list[CharacterRecord] = []
    for path in yaml_paths(names, root, "characters"):
        raw = read_yaml_mapping(archive, path)
        character_id = str(raw.get("id", ""))
        index_item = index.get(character_id)
        if index_item is None:
            raise PackageArchiveError(
                "PACKAGE_CHARACTER_INDEX_INVALID",
                f"character YAML 未在 characters/_index.yml 中声明: {character_id}",
            )
        records.append(character_record_from_mapping(raw, index_item))
    if len(records) == 0:
        raise PackageArchiveError("PACKAGE_CHARACTERS_REQUIRED", "剧本包至少需要一个角色 YAML")
    record_ids = frozenset(record.id for record in records)
    for character_id in sorted(set(index).difference(record_ids)):
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_INDEX_INVALID",
            f"characters/_index.yml 定义了缺失的角色 YAML: {character_id}",
        )
    return tuple(records)


def load_clues(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[ClueRecord, ...]:
    """将全部可见线索轮次 YAML 文件加载为规范化记录。"""

    records: list[ClueRecord] = []
    for path in yaml_paths(names, root, "clues/rounds"):
        records.extend(clue_records_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_evidences(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[EvidenceRecord, ...]:
    """将全部可见证物 YAML 文件加载为规范化记录。"""

    records: list[EvidenceRecord] = []
    for path in yaml_paths(names, root, "evidences"):
        records.append(evidence_record_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_scenes(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[SceneRecord, ...]:
    """将全部可见场景 YAML 文件加载为规范化记录。"""

    records: list[SceneRecord] = []
    for path in yaml_paths(names, root, "scenes"):
        records.append(scene_record_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_media_assets(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[MediaRecord, ...]:
    """将可选的音频和图像声明加载为媒体记录。"""

    records: list[MediaRecord] = []
    for path in yaml_paths(names, root, "media"):
        records.extend(media_records_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_endings(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[EndingRecord, ...]:
    """从剧本包根目录加载可选的结局定义。"""

    path = f"{root}endings.yml"
    if path not in names:
        return ()
    return ending_records_from_mapping(read_yaml_mapping(archive, path))


def load_assets(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[PackageAssetRecord, ...]:
    """加载已声明的归档资源并推断内容类型。"""

    prefix = f"{root}assets/"
    records: list[PackageAssetRecord] = []
    for name in sorted(item for item in names if item.startswith(prefix)):
        relative_path = name.removeprefix(root)
        records.append(
            PackageAssetRecord(
                path=relative_path,
                content=archive.read(name),
                content_type=mimetypes.guess_type(relative_path)[0] or "application/octet-stream",
            ),
        )
    return tuple(records)


def load_dm_guide(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> JsonMapping:
    """将可选的类型化 DM 私有指引文件加载为单一映射。"""

    prefix = f"{root}dm_guide/"
    dm_guide: JsonMapping = {}
    for path in sorted(name for name in names if name.startswith(prefix)):
        relative_path = path.removeprefix(prefix)
        if "/" in relative_path or not relative_path.endswith(".yml"):
            raise PackageArchiveError(
                "PACKAGE_DM_GUIDE_PATH_UNSUPPORTED",
                f"dm_guide 只接受根目录下文档规定的 .yml 文件: {relative_path}",
            )
        key = relative_path.removesuffix(".yml")
        dm_guide[key] = read_yaml_mapping(archive, path)
    return dm_guide


def package_config(
    package_yaml: JsonMapping,
    stage_index: JsonMapping,
    _dm_guide: JsonMapping,
) -> JsonMapping:
    """将已校验的阶段索引合并到持久化清单配置。"""

    config = dict(package_yaml)
    config["stage_index"] = stage_index
    return config


def relative_names(names: tuple[str, ...], root: str) -> frozenset[str]:
    """返回相对于剧本包根目录的可见归档成员名称。"""

    return frozenset(name.removeprefix(root) for name in names if name.startswith(root))


def _character_index(
    archive: ZipFile,
    root: str,
    names: tuple[str, ...],
) -> dict[str, CharacterIndexItem]:
    path = f"{root}characters/_index.yml"
    if path not in names:
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_INDEX_REQUIRED",
            "剧本包必须包含 characters/_index.yml",
        )
    index = CharacterIndex.model_validate(read_yaml_mapping(archive, path))
    if len(index.characters) == 0:
        raise PackageArchiveError(
            "PACKAGE_CHARACTER_INDEX_REQUIRED",
            "characters/_index.yml 必须定义 characters",
        )
    items: dict[str, CharacterIndexItem] = {}
    for item in index.characters:
        if item.id in items:
            raise PackageArchiveError(
                "PACKAGE_DUPLICATE_ID",
                f"characters/_index.yml 中重复的 character id: {item.id}",
            )
        items[item.id] = item
    return items
