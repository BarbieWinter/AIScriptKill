from engine.core.package_importer import prepare_package_for_import
from engine.core.package_loader import load_package_archive
from engine.core.package_schema import PackageAssetRecord
from engine.tests.package_loader_fixtures import minimal_package_files, package_archive


class FakePackageAssetStorage:
    def __init__(self) -> None:
        self.uploaded_assets: list[PackageAssetRecord] = []

    async def upload_asset(self, package_id: str, asset: PackageAssetRecord) -> str:
        self.uploaded_assets.append(asset)
        return f"https://storage.test/{package_id}/{asset.path}"


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
        prepared_package.dm_guide["truth"]["truth"]["alternative_endings"][0]["news_broadcast"]
        == "https://storage.test/minimal-case/assets/audio/ending.mp3"
    )
    assert prepared_package.package.config["dm_guide"] == prepared_package.dm_guide


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


def _package_files_with_assets() -> dict[str, str | bytes]:
    files: dict[str, str | bytes] = minimal_package_files()
    files["package.yml"] = files["package.yml"].replace(
        'engine:\n  entry_stage: "prologue"',
        'visual:\n  poster: "assets/posters/main.jpg"\nengine:\n  entry_stage: "prologue"',
    )
    files["clues/rounds/act1_round1.yml"] = files["clues/rounds/act1_round1.yml"].replace(
        'name: "线索一"',
        'name: "线索一"\n    image: "assets/clues/clue_1.jpg"',
    )
    files["scenes/main_hall.yml"] = files["scenes/main_hall.yml"].replace(
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
