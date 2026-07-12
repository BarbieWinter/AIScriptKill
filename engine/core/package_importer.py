"""准备私有资源并持久化一个已校验的剧本包导入。"""

from dataclasses import replace
from typing import Protocol

from engine.api.schemas.common import JsonValue
from engine.core.package_schema import (
    CharacterRecord,
    ClueRecord,
    EndingRecord,
    EvidenceRecord,
    JsonMapping,
    MediaRecord,
    PackageAssetRecord,
    SceneRecord,
    ScriptPackageImport,
    StageRecord,
)
from engine.db.protocols import WriteSession
from engine.rag.indexer import ScriptKnowledgeIndexRepository, index_package
from engine.rag.models import EmbeddingProvider
from engine.repositories.package_import_repository import PackageImportRepository


class PackageAssetStorage(Protocol):
    """存储剧本包资源并返回不透明的运行时定位符。"""

    async def upload_asset(self, package_id: str, asset: PackageAssetRecord) -> str:
        """在剧本包命名空间下上传一个资源。"""
        ...


async def prepare_package_for_import(
    package: ScriptPackageImport,
    asset_storage: PackageAssetStorage | None = None,
) -> ScriptPackageImport:
    """上传剧本包资源，并将匹配路径改写为私有定位符。"""

    if asset_storage is None or len(package.assets) == 0:
        return package

    asset_urls: dict[str, str] = {}
    for asset in package.assets:
        asset_urls[asset.path] = await asset_storage.upload_asset(package.package.id, asset)
    return _rewrite_package_asset_urls(package, asset_urls)


async def import_to_db(
    package: ScriptPackageImport,
    db: WriteSession,
    asset_storage: PackageAssetStorage | None = None,
    rag_embedding_provider: EmbeddingProvider | None = None,
) -> ScriptPackageImport:
    """持久化准备完成的剧本包，并可选择刷新其 RAG 索引。"""

    prepared_package = await prepare_package_for_import(package, asset_storage)
    await PackageImportRepository(db).import_package(prepared_package)
    if rag_embedding_provider is not None:
        await index_package(
            prepared_package,
            ScriptKnowledgeIndexRepository(db),
            rag_embedding_provider,
        )
    return prepared_package


def _rewrite_package_asset_urls(
    package: ScriptPackageImport,
    asset_urls: dict[str, str],
) -> ScriptPackageImport:
    return replace(
        package,
        package=replace(
            package.package,
            config=_rewrite_mapping(package.package.config, asset_urls),
        ),
        stages=tuple(_rewrite_stage(stage, asset_urls) for stage in package.stages),
        characters=tuple(
            _rewrite_character(character, asset_urls) for character in package.characters
        ),
        clues=tuple(_rewrite_clue(clue, asset_urls) for clue in package.clues),
        evidences=tuple(_rewrite_evidence(evidence, asset_urls) for evidence in package.evidences),
        scenes=tuple(_rewrite_scene(scene, asset_urls) for scene in package.scenes),
        media_assets=tuple(_rewrite_media(media, asset_urls) for media in package.media_assets),
        endings=tuple(_rewrite_ending(ending, asset_urls) for ending in package.endings),
        stage_index=_rewrite_mapping(package.stage_index, asset_urls),
        dm_guide=_rewrite_mapping(package.dm_guide, asset_urls),
    )


def _rewrite_stage(stage: StageRecord, asset_urls: dict[str, str]) -> StageRecord:
    return replace(stage, definition=_rewrite_mapping(stage.definition, asset_urls))


def _rewrite_character(character: CharacterRecord, asset_urls: dict[str, str]) -> CharacterRecord:
    return replace(character, definition=_rewrite_mapping(character.definition, asset_urls))


def _rewrite_clue(clue: ClueRecord, asset_urls: dict[str, str]) -> ClueRecord:
    return replace(
        clue,
        image_url=_rewrite_optional_asset_url(clue.image_url, asset_urls),
        metadata=_rewrite_mapping(clue.metadata, asset_urls),
    )


def _rewrite_evidence(evidence: EvidenceRecord, asset_urls: dict[str, str]) -> EvidenceRecord:
    return replace(
        evidence,
        image_url=_rewrite_optional_asset_url(evidence.image_url, asset_urls),
        metadata=_rewrite_mapping(evidence.metadata, asset_urls),
    )


def _rewrite_scene(scene: SceneRecord, asset_urls: dict[str, str]) -> SceneRecord:
    return replace(
        scene,
        background_url=_rewrite_optional_asset_url(scene.background_url, asset_urls),
        definition=_rewrite_mapping(scene.definition, asset_urls),
    )


def _rewrite_media(media: MediaRecord, asset_urls: dict[str, str]) -> MediaRecord:
    return replace(
        media,
        file_url=asset_urls.get(media.file_url, media.file_url),
        subtitle_url=_rewrite_optional_asset_url(media.subtitle_url, asset_urls),
        metadata=_rewrite_mapping(media.metadata, asset_urls),
    )


def _rewrite_ending(ending: EndingRecord, asset_urls: dict[str, str]) -> EndingRecord:
    return replace(
        ending,
        condition=_rewrite_mapping(ending.condition, asset_urls),
        on_trigger=tuple(_rewrite_mapping(event, asset_urls) for event in ending.on_trigger),
        metadata=_rewrite_mapping(ending.metadata, asset_urls),
    )


def _rewrite_optional_asset_url(value: str | None, asset_urls: dict[str, str]) -> str | None:
    if value is None:
        return None
    return asset_urls.get(value, value)


def _rewrite_mapping(mapping: JsonMapping, asset_urls: dict[str, str]) -> JsonMapping:
    rewritten = _rewrite_json_value(mapping, asset_urls)
    if isinstance(rewritten, dict):
        return rewritten
    return mapping


def _rewrite_json_value(value: JsonValue, asset_urls: dict[str, str]) -> JsonValue:
    if isinstance(value, str):
        return asset_urls.get(value, value)
    if isinstance(value, list):
        return [_rewrite_json_value(item, asset_urls) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_json_value(item, asset_urls) for key, item in value.items()}
    return value
