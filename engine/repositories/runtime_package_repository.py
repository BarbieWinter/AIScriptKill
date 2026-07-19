"""从规范化数据库行重建已发布的运行时剧本包。"""

from collections.abc import Sequence
from typing import cast

from sqlalchemy import and_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable

from engine.api.schemas.common import JsonValue
from engine.api.schemas.packages import PackageStatus
from engine.core.package_schema import (
    CharacterChapterRecord,
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    MediaRecord,
    PackageRecord,
    SceneRecord,
    ScriptPackageImport,
    StageRecord,
)
from engine.db.tables import (
    script_character_chapters,
    script_characters,
    script_clues,
    script_dm_guides,
    script_endings,
    script_evidences,
    script_media,
    script_packages,
    script_scenes,
    script_stages,
)


async def get_runtime_package(
    db: AsyncSession,
    script_id: str,
    *,
    lock_existing: bool = False,
) -> ScriptPackageImport | None:
    """Read a published runtime package, optionally holding its row ``FOR SHARE``."""

    package_statement = select(
        script_packages.c.id,
        script_packages.c.name,
        script_packages.c.version,
        script_packages.c.status,
        script_packages.c.config,
    ).where(
        and_(
            script_packages.c.id == script_id,
            script_packages.c.status == "published",
        )
    )
    if lock_existing:
        package_statement = package_statement.with_for_update(read=True)
    package_result = await db.execute(package_statement)
    package_row = package_result.mappings().one_or_none()
    if package_row is None:
        return None

    stages = await _rows(
        db,
        select(
            script_stages.c.stage_id,
            script_stages.c.name,
            script_stages.c.sort_order,
            script_stages.c.definition,
        )
        .where(script_stages.c.script_id == script_id)
        .order_by(script_stages.c.sort_order, script_stages.c.stage_id),
    )
    characters = await _rows(
        db,
        select(
            script_characters.c.character_id,
            script_characters.c.name,
            script_characters.c.definition,
            script_characters.c.is_playable,
            script_characters.c.is_dm_alter_ego,
            script_characters.c.sort_order,
        )
        .where(script_characters.c.script_id == script_id)
        .order_by(script_characters.c.sort_order, script_characters.c.character_id),
    )
    chapters = await _rows(
        db,
        select(
            script_character_chapters.c.chapter_id,
            script_character_chapters.c.character_id,
            script_character_chapters.c.sort_order,
            script_character_chapters.c.title,
            script_character_chapters.c.visibility,
            script_character_chapters.c.release,
            script_character_chapters.c.stage_min,
            script_character_chapters.c.content,
        )
        .where(script_character_chapters.c.script_id == script_id)
        .order_by(
            script_character_chapters.c.sort_order,
            script_character_chapters.c.chapter_id,
        ),
    )
    clues = await _rows(
        db,
        select(
            script_clues.c.clue_id,
            script_clues.c.name,
            script_clues.c.round_id,
            script_clues.c.image_url,
            script_clues.c.description,
            script_clues.c.is_key,
            script_clues.c.importance,
            script_clues.c.metadata,
        )
        .where(script_clues.c.script_id == script_id)
        .order_by(script_clues.c.round_id, script_clues.c.clue_id),
    )
    evidences = await _rows(
        db,
        select(
            script_evidences.c.evidence_id,
            script_evidences.c.name,
            script_evidences.c.image_url,
            script_evidences.c.description_surface,
            script_evidences.c.description_deep,
            script_evidences.c.type,
            script_evidences.c.metadata,
        )
        .where(script_evidences.c.script_id == script_id)
        .order_by(script_evidences.c.evidence_id),
    )
    scenes = await _rows(
        db,
        select(
            script_scenes.c.scene_id,
            script_scenes.c.name,
            script_scenes.c.background_url,
            script_scenes.c.definition,
        )
        .where(script_scenes.c.script_id == script_id)
        .order_by(script_scenes.c.scene_id),
    )
    media = await _rows(
        db,
        select(
            script_media.c.asset_id,
            script_media.c.type,
            script_media.c.file_url,
            script_media.c.subtitle_url,
            script_media.c.duration_sec,
            script_media.c.metadata,
        )
        .where(script_media.c.script_id == script_id)
        .order_by(script_media.c.asset_id),
    )
    endings = await _rows(
        db,
        select(
            script_endings.c.ending_id,
            script_endings.c.name,
            script_endings.c.condition,
            script_endings.c.on_trigger,
            script_endings.c.metadata,
        )
        .where(script_endings.c.script_id == script_id)
        .order_by(script_endings.c.ending_id),
    )
    guide_rows = await _rows(
        db,
        select(script_dm_guides.c.guide_key, script_dm_guides.c.content)
        .where(script_dm_guides.c.script_id == script_id)
        .order_by(script_dm_guides.c.guide_key),
    )
    config = _mapping(package_row["config"])
    return ScriptPackageImport(
        package=PackageRecord(
            id=str(package_row["id"]),
            title=str(package_row["name"]),
            version=str(package_row["version"]),
            status=_package_status(package_row["status"]),
            config=config,
        ),
        stages=tuple(
            StageRecord(
                id=str(row["stage_id"]),
                name=str(row["name"]),
                sort_order=int(row["sort_order"]),
                definition=_mapping(row["definition"]),
            )
            for row in stages
        ),
        characters=tuple(
            CharacterRecord(
                id=str(row["character_id"]),
                name=str(row["name"]),
                definition=_mapping(row["definition"]),
                is_playable=bool(row["is_playable"]),
                is_dm_alter_ego=bool(row["is_dm_alter_ego"]),
                sort_order=int(row["sort_order"]),
            )
            for row in characters
        ),
        chapters=tuple(_chapter(row) for row in chapters),
        clues=tuple(_clue(row) for row in clues),
        evidences=tuple(_evidence(row) for row in evidences),
        scenes=tuple(_scene(row) for row in scenes),
        media_assets=tuple(_media(row) for row in media),
        endings=tuple(_ending(row) for row in endings),
        stage_index=_mapping(config.get("stage_index")),
        dm_guide={str(row["guide_key"]): _json_value(row["content"]) for row in guide_rows},
    )


async def _rows(db: AsyncSession, statement: Executable) -> Sequence[RowMapping]:
    result = await db.execute(statement)
    return result.mappings().all()


def _chapter(row: RowMapping) -> CharacterChapterRecord:
    visibility = str(row["visibility"])
    if visibility != "character_only":
        raise RuntimePackageStorageError("chapter.visibility")
    return CharacterChapterRecord(
        id=str(row["chapter_id"]),
        character_id=str(row["character_id"]),
        sort_order=int(row["sort_order"]),
        title=str(row["title"]),
        visibility="character_only",
        release=_mapping(row["release"]),
        stage_min=str(row["stage_min"]) if row["stage_min"] is not None else None,
        content=str(row["content"]),
    )


def _clue(row: RowMapping) -> ClueRecord:
    return ClueRecord(
        id=str(row["clue_id"]),
        name=str(row["name"]),
        round_id=str(row["round_id"]),
        image_url=str(row["image_url"]) if row["image_url"] is not None else None,
        description=str(row["description"]),
        is_key=bool(row["is_key"]),
        importance=int(row["importance"]),
        metadata=_mapping(row["metadata"]),
    )


def _evidence(row: RowMapping) -> EvidenceRecord:
    return EvidenceRecord(
        id=str(row["evidence_id"]),
        name=str(row["name"]),
        image_url=str(row["image_url"]) if row["image_url"] is not None else None,
        description_surface=str(row["description_surface"]),
        description_deep=(
            str(row["description_deep"]) if row["description_deep"] is not None else None
        ),
        type=str(row["type"]),
        metadata=_mapping(row["metadata"]),
    )


def _scene(row: RowMapping) -> SceneRecord:
    return SceneRecord(
        id=str(row["scene_id"]),
        name=str(row["name"]),
        background_url=(str(row["background_url"]) if row["background_url"] is not None else None),
        definition=_mapping(row["definition"]),
    )


def _media(row: RowMapping) -> MediaRecord:
    media_type = str(row["type"])
    if media_type not in ("bgm", "story", "sfx", "voice", "image", "video"):
        raise RuntimePackageStorageError("media.type")
    return MediaRecord(
        id=str(row["asset_id"]),
        type=media_type,
        file_url=str(row["file_url"]),
        subtitle_url=str(row["subtitle_url"]) if row["subtitle_url"] is not None else None,
        duration_sec=float(row["duration_sec"]) if row["duration_sec"] is not None else None,
        metadata=_mapping(row["metadata"]),
    )


def _ending(row: RowMapping) -> EndingRecord:
    raw_actions = row["on_trigger"]
    if not isinstance(raw_actions, list):
        raise RuntimePackageStorageError("ending.on_trigger")
    actions: list[JsonMapping] = []
    for raw_action in cast(list[object], raw_actions):
        actions.append(_mapping(raw_action))
    return EndingRecord(
        id=str(row["ending_id"]),
        name=str(row["name"]),
        condition=_mapping(row["condition"]),
        on_trigger=tuple(actions),
        metadata=_mapping(row["metadata"]),
    )


def _mapping(value: object) -> JsonMapping:
    if not isinstance(value, dict):
        raise RuntimePackageStorageError("json_mapping")
    raw_mapping = cast(dict[object, object], value)
    result: JsonMapping = {}
    for key, item in raw_mapping.items():
        if not isinstance(key, str):
            raise RuntimePackageStorageError("json_mapping_key")
        result[key] = _json_value(item)
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        raw_sequence = cast(list[object] | tuple[object, ...], value)
        return [_json_value(item) for item in raw_sequence]
    if isinstance(value, dict):
        return _mapping(cast(dict[object, object], value))
    raise RuntimePackageStorageError("json_value")


def _package_status(value: object) -> PackageStatus:
    status = str(value)
    if status not in ("draft", "importing", "published", "archived"):
        raise RuntimePackageStorageError("package.status")
    return status


class RuntimePackageStorageError(Exception):
    """报告规范化剧本包行无法安全重建。"""

    def __init__(self, field: str) -> None:
        super().__init__(f"invalid runtime package field: {field}")
        self.field = field
