import mimetypes
from pathlib import Path
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
    index = _character_index(archive, root, names)
    records: list[CharacterRecord] = []
    for path in yaml_paths(names, root, "characters"):
        raw = read_yaml_mapping(archive, path)
        character_id = str(raw.get("id", ""))
        index_item = index.get(character_id, CharacterIndexItem(id=character_id))
        records.append(character_record_from_mapping(raw, index_item))
    if len(records) == 0:
        raise PackageArchiveError("PACKAGE_CHARACTERS_REQUIRED", "剧本包至少需要一个角色 YAML")
    return tuple(records)


def load_clues(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[ClueRecord, ...]:
    records: list[ClueRecord] = []
    for path in yaml_paths(names, root, "clues/rounds"):
        records.extend(clue_records_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_evidences(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for path in yaml_paths(names, root, "evidences"):
        records.append(evidence_record_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_scenes(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[SceneRecord, ...]:
    records: list[SceneRecord] = []
    for path in yaml_paths(names, root, "scenes"):
        records.append(scene_record_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_media_assets(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[MediaRecord, ...]:
    records: list[MediaRecord] = []
    for path in yaml_paths(names, root, "media"):
        records.extend(media_records_from_mapping(read_yaml_mapping(archive, path)))
    return tuple(records)


def load_endings(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[EndingRecord, ...]:
    path = f"{root}endings.yml"
    if path not in names:
        return ()
    return ending_records_from_mapping(read_yaml_mapping(archive, path))


def load_assets(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[PackageAssetRecord, ...]:
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
    dm_guide: JsonMapping = {}
    for path in yaml_paths(names, root, "dm_guide"):
        key = Path(path).stem
        dm_guide[key] = read_yaml_mapping(archive, path)
    return dm_guide


def package_config(
    package_yaml: JsonMapping,
    stage_index: JsonMapping,
    dm_guide: JsonMapping,
) -> JsonMapping:
    config = dict(package_yaml)
    config["stage_index"] = stage_index
    if len(dm_guide) > 0:
        config["dm_guide"] = dm_guide
    return config


def relative_names(names: tuple[str, ...], root: str) -> frozenset[str]:
    return frozenset(name.removeprefix(root) for name in names if name.startswith(root))


def _character_index(
    archive: ZipFile,
    root: str,
    names: tuple[str, ...],
) -> dict[str, CharacterIndexItem]:
    path = f"{root}characters/_index.yml"
    if path not in names:
        return {}
    index = CharacterIndex.model_validate(read_yaml_mapping(archive, path))
    return {item.id: item for item in index.characters}
