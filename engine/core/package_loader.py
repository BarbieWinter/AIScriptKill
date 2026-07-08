from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from pydantic import ValidationError

from engine.api.schemas.packages import PackageStatus
from engine.core.package_archive import (
    PackageArchiveError,
    package_path,
    read_yaml_mapping,
    visible_file,
)
from engine.core.package_content_loader import (
    load_assets,
    load_characters,
    load_clues,
    load_dm_guide,
    load_endings,
    load_evidences,
    load_media_assets,
    load_scenes,
    package_config,
    relative_names,
)
from engine.core.package_directory import package_directory_archive
from engine.core.package_schema import PackageRecord, ScriptPackageImport
from engine.core.package_stage_loader import (
    load_stage_index,
    load_stages,
)
from engine.core.package_validation import validate_package_import
from engine.core.package_yaml import PackageManifest

# ── ZIP 入口 ──


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


def load_package_directory(package_dir: Path, publish: bool = False) -> ScriptPackageImport:
    return load_package_archive(package_directory_archive(package_dir), publish)


def _load_package(
    archive: ZipFile,
    names: tuple[str, ...],
    root: str,
    package_path: str,
    publish: bool,
) -> ScriptPackageImport:
    package_yaml = read_yaml_mapping(archive, package_path)
    manifest = PackageManifest.model_validate(package_yaml)
    stage_index = load_stage_index(archive, names, root)
    dm_guide = load_dm_guide(archive, names, root)
    package = ScriptPackageImport(
        package=PackageRecord(
            id=manifest.metadata.id,
            title=manifest.metadata.title,
            version=manifest.metadata.version,
            status=_package_status(publish),
            config=package_config(package_yaml, stage_index, dm_guide),
        ),
        stages=load_stages(archive, names, root, stage_index),
        characters=load_characters(archive, names, root),
        clues=load_clues(archive, names, root),
        evidences=load_evidences(archive, names, root),
        scenes=load_scenes(archive, names, root),
        media_assets=load_media_assets(archive, names, root),
        endings=load_endings(archive, names, root),
        stage_index=stage_index,
        dm_guide=dm_guide,
        assets=load_assets(archive, names, root),
    )
    warnings = validate_package_import(package, available_files=relative_names(names, root))
    if len(warnings) == 0:
        return package
    return ScriptPackageImport(
        package=package.package,
        stages=package.stages,
        characters=package.characters,
        clues=package.clues,
        evidences=package.evidences,
        scenes=package.scenes,
        media_assets=package.media_assets,
        endings=package.endings,
        stage_index=package.stage_index,
        dm_guide=package.dm_guide,
        assets=package.assets,
        warnings=warnings,
    )


def _package_status(publish: bool) -> PackageStatus:
    if publish:
        return "published"
    return "draft"
