from typing import cast

from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Executable
from sqlalchemy.sql.selectable import Select

from engine.core.package_schema import ScriptPackageImport
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.tests.stategraph_fixtures import state_graph_package


class _FakeResult:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def mappings(self) -> "_FakeResult":
        return self

    def one_or_none(self) -> dict[str, object] | None:
        if not self._rows:
            return None
        return self._rows[0]

    def all(self) -> list[dict[str, object]]:
        return list(self._rows)


class _RuntimePackageDb:
    def __init__(self, published: bool = True) -> None:
        self.package = state_graph_package()
        self.published = published

    async def execute(self, statement: Executable) -> _FakeResult:
        table = _select_table(statement)
        if table == "script_packages":
            if not self.published:
                return _FakeResult([])
            record = self.package.package
            return _FakeResult(
                [
                    {
                        "id": record.id,
                        "name": record.title,
                        "version": record.version,
                        "status": "published",
                        "config": record.config,
                    }
                ]
            )
        return _FakeResult(_table_rows(self.package, table))


def _select_table(statement: Executable) -> str:
    selectable = cast(Select[tuple[object, ...]], statement)
    sql = str(selectable.compile(dialect=postgresql.dialect()))
    for table_name in (
        "script_packages",
        "script_stages",
        "script_characters",
        "script_character_chapters",
        "script_clues",
        "script_evidences",
        "script_scenes",
        "script_media",
        "script_endings",
        "script_dm_guides",
    ):
        if f"FROM {table_name}" in sql:
            return table_name
    raise AssertionError(sql)


def _table_rows(package: ScriptPackageImport, table: str) -> list[dict[str, object]]:
    if table == "script_stages":
        return [
            {
                "stage_id": item.id,
                "name": item.name,
                "sort_order": item.sort_order,
                "definition": item.definition,
            }
            for item in package.stages
        ]
    if table == "script_characters":
        return [
            {
                "character_id": item.id,
                "name": item.name,
                "definition": item.definition,
                "is_playable": item.is_playable,
                "is_dm_alter_ego": item.is_dm_alter_ego,
                "sort_order": item.sort_order,
            }
            for item in package.characters
        ]
    if table == "script_clues":
        return [
            {
                "clue_id": item.id,
                "name": item.name,
                "round_id": item.round_id,
                "image_url": item.image_url,
                "description": item.description,
                "is_key": item.is_key,
                "importance": item.importance,
                "metadata": item.metadata,
            }
            for item in package.clues
        ]
    if table == "script_evidences":
        return [
            {
                "evidence_id": item.id,
                "name": item.name,
                "image_url": item.image_url,
                "description_surface": item.description_surface,
                "description_deep": item.description_deep,
                "type": item.type,
                "metadata": item.metadata,
            }
            for item in package.evidences
        ]
    if table == "script_scenes":
        return [
            {
                "scene_id": item.id,
                "name": item.name,
                "background_url": item.background_url,
                "definition": item.definition,
            }
            for item in package.scenes
        ]
    if table == "script_media":
        return [
            {
                "asset_id": item.id,
                "type": item.type,
                "file_url": item.file_url,
                "subtitle_url": item.subtitle_url,
                "duration_sec": item.duration_sec,
                "metadata": item.metadata,
            }
            for item in package.media_assets
        ]
    if table == "script_endings":
        return [
            {
                "ending_id": item.id,
                "name": item.name,
                "condition": item.condition,
                "on_trigger": list(item.on_trigger),
                "metadata": item.metadata,
            }
            for item in package.endings
        ]
    return []


async def test_runtime_package_repository_reconstructs_full_published_package() -> None:
    original = state_graph_package()
    loaded = await get_runtime_package(
        cast(AsyncSession, cast(object, _RuntimePackageDb())),
        original.package.id,
    )

    assert loaded is not None
    assert loaded.package.id == original.package.id
    assert loaded.package.title == original.package.title
    assert loaded.package.version == original.package.version
    assert loaded.package.status == "published"
    assert loaded.package.config == original.package.config
    assert loaded.stages == original.stages
    assert loaded.characters == original.characters
    assert loaded.clues == original.clues
    assert loaded.evidences == original.evidences
    assert loaded.media_assets == original.media_assets
    assert loaded.endings == original.endings
    assert loaded.stage_index == original.stage_index


async def test_runtime_package_repository_rejects_unpublished_package() -> None:
    loaded = await get_runtime_package(
        cast(AsyncSession, cast(object, _RuntimePackageDb(published=False))),
        "minimal-case",
    )

    assert loaded is None
