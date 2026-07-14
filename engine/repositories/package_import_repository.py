from sqlalchemy import delete, func, insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

from engine.core.package_schema import ScriptPackageImport
from engine.db.protocols import WriteSession
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

# ── 剧本包导入 Repository ──


class PackageImportRepository:
    def __init__(self, db: WriteSession) -> None:
        self._db = db

    async def import_package(self, package: ScriptPackageImport) -> None:
        await self._upsert_package(package)
        await self._replace_structure(package)
        await self._db.commit()

    async def _upsert_package(self, package: ScriptPackageImport) -> None:
        record = package.package
        stmt = (
            pg_insert(script_packages)
            .values(
                id=record.id,
                name=record.title,
                version=record.version,
                config=record.config,
                status=record.status,
            )
            .on_conflict_do_update(
                index_elements=[script_packages.c.id],
                set_={
                    "name": record.title,
                    "version": record.version,
                    "config": record.config,
                    "status": record.status,
                    "updated_at": func.now(),
                },
            )
        )
        await self._db.execute(stmt)

    async def _replace_structure(self, package: ScriptPackageImport) -> None:
        script_id = package.package.id
        await self._delete_structure(script_id)
        for stage in package.stages:
            await self._db.execute(
                insert(script_stages).values(
                    script_id=script_id,
                    stage_id=stage.id,
                    name=stage.name,
                    sort_order=stage.sort_order,
                    definition=stage.definition,
                ),
            )
        for character in package.characters:
            await self._db.execute(
                insert(script_characters).values(
                    script_id=script_id,
                    character_id=character.id,
                    name=character.name,
                    definition=character.definition,
                    is_playable=character.is_playable,
                    is_dm_alter_ego=character.is_dm_alter_ego,
                    sort_order=character.sort_order,
                ),
            )
        for chapter in package.chapters:
            await self._db.execute(
                insert(script_character_chapters).values(
                    script_id=script_id,
                    chapter_id=chapter.id,
                    character_id=chapter.character_id,
                    sort_order=chapter.sort_order,
                    title=chapter.title,
                    visibility=chapter.visibility,
                    release=chapter.release,
                    stage_min=chapter.stage_min,
                    content=chapter.content,
                ),
            )
        await self._insert_optional_structure(package)

    async def _insert_optional_structure(self, package: ScriptPackageImport) -> None:
        script_id = package.package.id
        for clue in package.clues:
            await self._db.execute(
                insert(script_clues).values(
                    script_id=script_id,
                    clue_id=clue.id,
                    name=clue.name,
                    round_id=clue.round_id,
                    image_url=clue.image_url,
                    description=clue.description,
                    is_key=clue.is_key,
                    importance=clue.importance,
                    metadata=clue.metadata,
                ),
            )
        for evidence in package.evidences:
            await self._db.execute(
                insert(script_evidences).values(
                    script_id=script_id,
                    evidence_id=evidence.id,
                    name=evidence.name,
                    image_url=evidence.image_url,
                    description_surface=evidence.description_surface,
                    description_deep=evidence.description_deep,
                    type=evidence.type,
                    metadata=evidence.metadata,
                ),
            )
        await self._insert_media_structure(package)

    async def _insert_media_structure(self, package: ScriptPackageImport) -> None:
        script_id = package.package.id
        for scene in package.scenes:
            await self._db.execute(
                insert(script_scenes).values(
                    script_id=script_id,
                    scene_id=scene.id,
                    name=scene.name,
                    background_url=scene.background_url,
                    definition=scene.definition,
                ),
            )
        for media in package.media_assets:
            await self._db.execute(
                insert(script_media).values(
                    script_id=script_id,
                    asset_id=media.id,
                    type=media.type,
                    file_url=media.file_url,
                    subtitle_url=media.subtitle_url,
                    duration_sec=media.duration_sec,
                    metadata=media.metadata,
                ),
            )
        await self._insert_resolution_structure(package)

    async def _insert_resolution_structure(self, package: ScriptPackageImport) -> None:
        script_id = package.package.id
        for ending in package.endings:
            await self._db.execute(
                insert(script_endings).values(
                    script_id=script_id,
                    ending_id=ending.id,
                    name=ending.name,
                    condition=ending.condition,
                    on_trigger=list(ending.on_trigger),
                    metadata=ending.metadata,
                ),
            )
        for guide_key, content in package.dm_guide.items():
            await self._db.execute(
                insert(script_dm_guides).values(
                    script_id=script_id,
                    guide_key=guide_key,
                    content=content,
                ),
            )

    async def _delete_structure(self, script_id: str) -> None:
        for table in (
            script_dm_guides,
            script_endings,
            script_media,
            script_scenes,
            script_evidences,
            script_clues,
            script_character_chapters,
            script_characters,
            script_stages,
        ):
            await self._db.execute(delete(table).where(table.c.script_id == script_id))
