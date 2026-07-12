"""校验剧本包资源引用和角色知识覆盖范围。"""

from engine.core.package_archive import PackageArchiveError
from engine.core.package_schema import ScriptPackageImport
from engine.core.package_validation_context import PackageValidationContext
from engine.core.package_yaml import CharacterDefinition, PackageManifest


def validate_asset_paths(
    package: ScriptPackageImport,
    manifest: PackageManifest,
    context: PackageValidationContext,
) -> None:
    """根据归档成员校验每个已建模的本地资源路径。"""

    validate_asset_path_reference("package visual.poster", manifest.visual.poster, context)
    for clue in package.clues:
        validate_asset_path_reference(f"clue {clue.id} image", clue.image_url, context)
    for evidence in package.evidences:
        validate_asset_path_reference(f"evidence {evidence.id} image", evidence.image_url, context)
    for scene in package.scenes:
        validate_asset_path_reference(f"scene {scene.id} background", scene.background_url, context)
    for media in package.media_assets:
        validate_asset_path_reference(f"media {media.id} file", media.file_url, context)
        validate_asset_path_reference(f"media {media.id} subtitle", media.subtitle_url, context)


def character_knowledge_warnings(
    package: ScriptPackageImport,
    context: PackageValidationContext,
) -> tuple[str, ...]:
    """返回角色知识缺少索引阶段的警告。"""

    warnings: list[str] = []
    for character in package.characters:
        definition = CharacterDefinition.model_validate(character.definition)
        known_stage_ids = frozenset(
            knowledge_stage_id(stage_key) for stage_key in definition.knowledge
        )
        missing_stage_ids = sorted(context.stage_ids.difference(known_stage_ids))
        if len(missing_stage_ids) > 0:
            warnings.append(
                f"character {character.id} 缺少阶段知识: {', '.join(missing_stage_ids)}",
            )
    return tuple(warnings)


def validate_asset_path_reference(
    owner: str,
    path: str | None,
    context: PackageValidationContext,
) -> None:
    """允许外部资源，否则要求本地路径存在于剧本包中。"""

    if path is None or _external_asset_path(path) or len(context.available_files) == 0:
        return
    if path in context.available_files:
        return
    raise PackageArchiveError("PACKAGE_ASSET_MISSING", f"{owner} 指向不存在的素材文件: {path}")


def _external_asset_path(path: str) -> bool:
    return path.startswith(("http://", "https://", "/"))


def knowledge_stage_id(stage_key: str) -> str:
    """将兼容的 ``stage_<id>`` 知识键归一化为权威阶段 ID。"""

    if stage_key.startswith("stage_"):
        return stage_key.removeprefix("stage_")
    return stage_key
