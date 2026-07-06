from collections.abc import Iterable
from io import BytesIO
from typing import Final
from zipfile import BadZipFile, ZipFile

from pydantic import ValidationError

from engine.api.schemas.common import JsonValue
from engine.api.schemas.packages import PackageStatus
from engine.core.package_archive import (
    PackageArchiveError,
    package_path,
    read_yaml_mapping,
    visible_file,
    yaml_paths,
)
from engine.core.package_schema import (
    CharacterDefinition,
    CharacterIndex,
    CharacterIndexItem,
    CharacterRecord,
    ClueRecord,
    ClueRoundDefinition,
    EvidenceDefinition,
    EvidenceRecord,
    JsonMapping,
    MediaAsset,
    MediaFileDefinition,
    MediaRecord,
    MediaType,
    PackageManifest,
    PackageRecord,
    SceneDefinition,
    SceneRecord,
    ScriptPackageImport,
    StageDefinition,
    StageRecord,
)

# ── ZIP 入口 ──

MEDIA_TYPES: Final[frozenset[MediaType]] = frozenset(
    ("bgm", "story", "sfx", "voice", "image", "video"),
)


def load_package_archive(archive_bytes: bytes, publish: bool = False) -> ScriptPackageImport:
    try:
        with ZipFile(BytesIO(archive_bytes)) as archive:
            names = tuple(name for name in archive.namelist() if visible_file(name))
            manifest_path = package_path(names)
            package_root = manifest_path.removesuffix("package.yml")
            return _load_package(archive, names, package_root, manifest_path, publish)
    except BadZipFile as exc:
        raise PackageArchiveError("INVALID_PACKAGE_ZIP", "上传文件不是有效的 zip 剧本包") from exc
    except ValidationError as exc:
        raise PackageArchiveError("INVALID_PACKAGE_SCHEMA", str(exc)) from exc


def _load_package(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
    package_path: str,
    publish: bool,
) -> ScriptPackageImport:
    package_yaml = read_yaml_mapping(archive, package_path)
    manifest = PackageManifest.model_validate(package_yaml)
    return ScriptPackageImport(
        package=PackageRecord(
            id=manifest.metadata.id,
            title=manifest.metadata.title,
            version=manifest.metadata.version,
            status=_package_status(publish),
            config=package_yaml,
        ),
        stages=_load_stages(archive, names, root),
        characters=_load_characters(archive, names, root),
        clues=_load_clues(archive, names, root),
        evidences=_load_evidences(archive, names, root),
        scenes=_load_scenes(archive, names, root),
        media_assets=_load_media_assets(archive, names, root),
    )


# ── 结构表记录解析 ──


def _load_stages(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[StageRecord, ...]:
    records: list[StageRecord] = []
    for path in yaml_paths(names, root, "stages"):
        raw = read_yaml_mapping(archive, path)
        stage = StageDefinition.model_validate(raw)
        records.append(
            StageRecord(
                id=stage.id,
                name=stage.name,
                sort_order=stage.sort_order,
                definition=raw,
            ),
        )
    if len(records) == 0:
        raise PackageArchiveError("PACKAGE_STAGES_REQUIRED", "剧本包至少需要一个 stage YAML")
    return tuple(records)


def _load_characters(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[CharacterRecord, ...]:
    index = _character_index(archive, root, names)
    records: list[CharacterRecord] = []
    for path in yaml_paths(names, root, "characters"):
        raw = read_yaml_mapping(archive, path)
        character = CharacterDefinition.model_validate(raw)
        index_item = index.get(character.id, CharacterIndexItem(id=character.id))
        records.append(
            CharacterRecord(
                id=character.id,
                name=character.name,
                definition=raw,
                is_playable=index_item.playable,
                is_dm_alter_ego=character.is_dm_alter_ego or index_item.is_dm_alter_ego,
                sort_order=index_item.order,
            ),
        )
    if len(records) == 0:
        raise PackageArchiveError("PACKAGE_CHARACTERS_REQUIRED", "剧本包至少需要一个角色 YAML")
    return tuple(records)


def _load_clues(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[ClueRecord, ...]:
    records: list[ClueRecord] = []
    for path in yaml_paths(names, root, "clues/rounds"):
        raw = read_yaml_mapping(archive, path)
        clue_round = ClueRoundDefinition.model_validate(raw)
        records.extend(_clue_records(clue_round))
    return tuple(records)


def _load_evidences(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[EvidenceRecord, ...]:
    records: list[EvidenceRecord] = []
    for path in yaml_paths(names, root, "evidences"):
        raw = read_yaml_mapping(archive, path)
        evidence = EvidenceDefinition.model_validate(raw)
        records.append(
            EvidenceRecord(
                id=evidence.id,
                name=evidence.name,
                image_url=evidence.visual.image,
                description_surface=evidence.description.surface,
                description_deep=evidence.description.deep,
                type=evidence.type,
                metadata=raw,
            ),
        )
    return tuple(records)


def _load_scenes(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[SceneRecord, ...]:
    records: list[SceneRecord] = []
    for path in yaml_paths(names, root, "scenes"):
        raw = read_yaml_mapping(archive, path)
        scene = SceneDefinition.model_validate(raw)
        records.append(
            SceneRecord(
                id=scene.id,
                name=scene.name,
                background_url=scene.visual.background,
                definition=raw,
            ),
        )
    return tuple(records)


def _load_media_assets(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
) -> tuple[MediaRecord, ...]:
    records: list[MediaRecord] = []
    for path in yaml_paths(names, root, "media"):
        media_file = MediaFileDefinition.model_validate(read_yaml_mapping(archive, path))
        records.extend(_audio_records(media_file.audio_assets))
        records.extend(_image_records(media_file.image_assets))
    return tuple(records)


# ── 单项记录构造 ──


def _clue_records(clue_round: ClueRoundDefinition) -> Iterable[ClueRecord]:
    for clue in clue_round.clues:
        related_characters: list[JsonValue] = [character for character in clue.related_characters]
        metadata: JsonMapping = {
            "stage_visible": clue_round.stage_visible,
            "visibility": "public",
            "round_name": clue_round.name,
            "related_scene": clue.related_scene,
            "related_characters": related_characters,
        }
        yield ClueRecord(
            id=clue.id,
            name=clue.name,
            round_id=clue_round.round_id,
            image_url=clue.image,
            description=clue.description,
            is_key=clue.key_clue,
            importance=clue.importance,
            metadata=metadata,
        )


def _audio_records(assets: list[MediaAsset]) -> Iterable[MediaRecord]:
    for asset in assets:
        yield MediaRecord(
            id=asset.id,
            type=_media_type(asset.type),
            file_url=asset.file,
            subtitle_url=asset.subtitle_file,
            duration_sec=asset.duration_sec,
            metadata=asset.model_dump(mode="json"),
        )


def _image_records(assets: list[MediaAsset]) -> Iterable[MediaRecord]:
    for asset in assets:
        metadata = asset.model_dump(mode="json")
        metadata["original_type"] = asset.type
        yield MediaRecord(
            id=asset.id,
            type="image",
            file_url=asset.file,
            subtitle_url=None,
            duration_sec=asset.duration_sec,
            metadata=metadata,
        )


# ── YAML 与路径工具 ──


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


def _package_status(publish: bool) -> PackageStatus:
    if publish:
        return "published"
    return "draft"


def _media_type(value: str) -> MediaType:
    if value not in MEDIA_TYPES:
        raise PackageArchiveError("INVALID_MEDIA_TYPE", f"不支持的媒体类型: {value}")
    return value
