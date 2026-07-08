from sqlalchemy import Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import Executable
from sqlalchemy.sql.dml import Delete, Insert

from engine.core.package_importer import import_to_db, prepare_package_for_import
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import JsonMapping, PackageAssetRecord
from engine.rag.embeddings import DeterministicEmbeddingProvider
from engine.rag.metadata import json_mapping, json_mapping_list
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive
from engine.tests.rag_fixtures import rag_package


class FakePackageAssetStorage:
    def __init__(self) -> None:
        self.uploaded_assets: list[PackageAssetRecord] = []

    async def upload_asset(self, package_id: str, asset: PackageAssetRecord) -> str:
        self.uploaded_assets.append(asset)
        return f"https://storage.test/{package_id}/{asset.path}"


class RecordingAsyncSession:
    def __init__(self) -> None:
        self.statements: list[Executable] = []
        self.commit_count = 0

    async def execute(self, statement: Executable) -> None:
        self.statements.append(statement)

    async def commit(self) -> None:
        self.commit_count += 1


async def test_prepare_package_for_import_uploads_assets_and_rewrites_local_paths() -> None:
    # Given: a loaded package references local files from multiple import records.
    package = load_package_archive(package_archive(_package_files_with_assets()))
    storage = FakePackageAssetStorage()

    # When: the package is prepared with an asset storage backend.
    prepared_package = await prepare_package_for_import(package, storage)

    # Then: every package asset is uploaded once and matching YAML paths become runtime URLs.
    assert [asset.path for asset in storage.uploaded_assets] == [
        "assets/audio/ending.mp3",
        "assets/audio/intro.mp3",
        "assets/audio/intro.vtt",
        "assets/clues/clue_1.jpg",
        "assets/evidences/knife.jpg",
        "assets/images/overview.png",
        "assets/posters/main.jpg",
        "assets/scenes/main_hall.jpg",
    ]
    assert prepared_package.package.config["visual"] == {
        "poster": "https://storage.test/minimal-case/assets/posters/main.jpg",
    }

    first_clue = next(clue for clue in prepared_package.clues if clue.id == "clue_1")
    assert first_clue.image_url == "https://storage.test/minimal-case/assets/clues/clue_1.jpg"

    evidence = prepared_package.evidences[0]
    assert evidence.image_url == "https://storage.test/minimal-case/assets/evidences/knife.jpg"
    assert evidence.metadata["visual"] == {
        "image": "https://storage.test/minimal-case/assets/evidences/knife.jpg",
    }

    scene = prepared_package.scenes[0]
    assert scene.background_url == "https://storage.test/minimal-case/assets/scenes/main_hall.jpg"
    assert scene.definition["visual"] == {
        "background": "https://storage.test/minimal-case/assets/scenes/main_hall.jpg",
    }

    media = {asset.id: asset for asset in prepared_package.media_assets}
    assert media["intro"].file_url == "https://storage.test/minimal-case/assets/audio/intro.mp3"
    assert media["intro"].subtitle_url == "https://storage.test/minimal-case/assets/audio/intro.vtt"
    assert (
        media["overview"].file_url == "https://storage.test/minimal-case/assets/images/overview.png"
    )
    assert media["overview"].metadata["file"] == (
        "https://storage.test/minimal-case/assets/images/overview.png"
    )
    assert (
        _dm_guide_news_broadcast(prepared_package.dm_guide)
        == "https://storage.test/minimal-case/assets/audio/ending.mp3"
    )
    assert "dm_guide" not in prepared_package.package.config


async def test_import_to_db_persists_endings_and_privileged_dm_guide() -> None:
    package = load_package_archive(package_archive(_package_files_with_assets()))
    session = RecordingAsyncSession()

    prepared_package = await import_to_db(package, session)

    package_params = _insert_params(session, "script_packages")[0]
    package_config = package_params["config"]
    assert isinstance(package_config, dict)
    assert "dm_guide" not in package_config

    ending_params = _insert_params(session, "script_endings")
    assert ending_params == [
        {
            "script_id": "minimal-case",
            "ending_id": "truth",
            "name": "真相复盘",
            "condition": {"type": "submission_correct", "field": "suspect", "value": "npc"},
            "on_trigger": [{"action": "transition_to", "stage_id": "review"}],
            "metadata": prepared_package.endings[0].metadata,
        },
    ]

    guide_params = _insert_params(session, "script_dm_guides")
    assert guide_params == [
        {
            "script_id": "minimal-case",
            "guide_key": "truth",
            "content": prepared_package.dm_guide["truth"],
        },
    ]
    assert session.commit_count == 1


async def test_import_to_db_replaces_endings_and_dm_guide_on_repeated_import() -> None:
    package = load_package_archive(package_archive(_package_files_with_assets()))
    session = RecordingAsyncSession()

    await import_to_db(package, session)
    await import_to_db(package, session)

    deleted_tables = [
        table_name
        for statement in session.statements
        if isinstance(statement, Delete)
        if (table_name := _table_name(statement)) is not None
    ]
    assert deleted_tables.count("script_endings") == 2
    assert deleted_tables.count("script_dm_guides") == 2
    assert len(_insert_params(session, "script_endings")) == 2
    assert len(_insert_params(session, "script_dm_guides")) == 2
    assert session.commit_count == 2


async def test_import_to_db_indexes_rag_knowledge_when_embedding_provider_is_supplied() -> None:
    # Given: a loaded package contains DM-only truth material for RAG.
    package = rag_package()
    session = RecordingAsyncSession()

    # When: the importer receives an embedding provider.
    await import_to_db(
        package,
        session,
        rag_embedding_provider=DeterministicEmbeddingProvider(),
    )

    # Then: script_knowledge receives embedded chunks without leaking truth metadata.
    knowledge_params = _insert_params(session, "script_knowledge")
    truth_params = [
        params for params in knowledge_params if "NPC角色是凶手" in str(params["chunk_text"])
    ]
    assert len(knowledge_params) > 0
    assert len(truth_params) > 0
    assert all(_metadata_visibility(params) == "dm_only" for params in truth_params)
    assert all(_embedding_length(params) == 1536 for params in knowledge_params)
    assert session.commit_count == 2


async def test_prepare_package_for_import_without_storage_keeps_package_unchanged() -> None:
    # Given: a package contains local assets but no storage backend is configured.
    package = load_package_archive(package_archive(_package_files_with_assets()))

    # When: the package is prepared without storage.
    prepared_package = await prepare_package_for_import(package)

    # Then: the caller can still use the existing local-path placeholder behavior.
    assert prepared_package is package


def test_load_package_archive_collects_assets_from_package_assets_directory() -> None:
    # Given: a package includes binary files under assets/.
    package = load_package_archive(package_archive(_package_files_with_assets()))

    # Then: loader exposes upload-ready asset records separately from YAML records.
    assets = {asset.path: asset for asset in package.assets}
    assert assets["assets/posters/main.jpg"].content == b"poster"
    assert assets["assets/posters/main.jpg"].content_type == "image/jpeg"
    assert assets["assets/audio/intro.mp3"].content == b"intro"
    assert assets["assets/audio/intro.mp3"].content_type == "audio/mpeg"


def _insert_params(session: RecordingAsyncSession, table_name: str) -> list[dict[str, object]]:
    return [
        dict(statement.compile(dialect=postgresql.dialect()).params)
        for statement in session.statements
        if isinstance(statement, Insert) and _table_name(statement) == table_name
    ]


def _table_name(statement: Executable) -> str | None:
    table = getattr(statement, "table", None)
    if isinstance(table, Table):
        return table.name
    return None


def _metadata_visibility(params: dict[str, object]) -> str:
    metadata = params["metadata"]
    assert isinstance(metadata, dict)
    visibility = metadata["visibility"]
    assert isinstance(visibility, str)
    return visibility


def _embedding_length(params: dict[str, object]) -> int:
    embedding = params["embedding"]
    assert isinstance(embedding, list)
    return len(embedding)


def _dm_guide_news_broadcast(dm_guide: JsonMapping) -> str:
    truth = json_mapping(dm_guide.get("truth"))
    truth_body = json_mapping(truth.get("truth"))
    alternative_endings = json_mapping_list(truth_body.get("alternative_endings"))
    news_broadcast = alternative_endings[0]["news_broadcast"]
    assert isinstance(news_broadcast, str)
    return news_broadcast


def _text_file(files: dict[str, str | bytes], path: str) -> str:
    content = files[path]
    assert isinstance(content, str)
    return content


def _package_files_with_assets() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = dict(minimal_package_files())
    files["package.yml"] = _text_file(files, "package.yml").replace(
        'engine:\n  entry_stage: "prologue"',
        'visual:\n  poster: "assets/posters/main.jpg"\nengine:\n  entry_stage: "prologue"',
    )
    files["clues/rounds/act1_round1.yml"] = _text_file(
        files,
        "clues/rounds/act1_round1.yml",
    ).replace(
        'name: "线索一"',
        'name: "线索一"\n    image: "assets/clues/clue_1.jpg"',
    )
    files["scenes/main_hall.yml"] = _text_file(files, "scenes/main_hall.yml").replace(
        'name: "大厅"',
        'name: "大厅"\nvisual:\n  background: "assets/scenes/main_hall.jpg"',
    )
    files["evidences/knife.yml"] = """
id: "knife"
name: "刀"
visual:
  image: "assets/evidences/knife.jpg"
description:
  surface: "一把刀"
discovery:
  scene_id: "main_hall"
"""
    files["media/default.yml"] = """
audio_assets:
  - id: "intro"
    type: "bgm"
    file: "assets/audio/intro.mp3"
    subtitle_file: "assets/audio/intro.vtt"
image_assets:
  - id: "overview"
    type: "image"
    file: "assets/images/overview.png"
"""
    files["dm_guide/truth.yml"] = """
truth:
  alternative_endings:
    - id: "ending_caught"
      condition: "player_correct_all"
      news_broadcast: "assets/audio/ending.mp3"
"""
    files["assets/audio/ending.mp3"] = b"ending"
    files["assets/audio/intro.mp3"] = b"intro"
    files["assets/audio/intro.vtt"] = b"WEBVTT"
    files["assets/clues/clue_1.jpg"] = b"clue"
    files["assets/evidences/knife.jpg"] = b"knife"
    files["assets/images/overview.png"] = b"overview"
    files["assets/posters/main.jpg"] = b"poster"
    files["assets/scenes/main_hall.jpg"] = b"scene"
    return files
