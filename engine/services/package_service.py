"""协调剧本包校验、私有存储和持久化。"""

from typing import cast

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import not_found, unprocessable_entity
from engine.api.schemas import PackageListResponse
from engine.api.schemas.packages import (
    PackagePlayableCharactersResponse,
    PackageSummary,
    PackageUpdateRequest,
    PackageUpdateResponse,
    PlayableCharacterSummary,
)
from engine.core.package_multiplayer import multiplayer_package_playability
from engine.repositories.package_repository import (
    PackageRepository,
    StoredPackage,
    StoredPackageStatus,
    StoredPlayableCharacter,
)
from engine.repositories.runtime_package_repository import get_runtime_package
from engine.services.mapper_utils import timestamp

# ── 剧本包列表服务 ──


async def list_packages(db: AsyncSession) -> PackageListResponse:
    """以公开目录结构返回全部已发布剧本包。"""

    repository = PackageRepository(db)
    packages = await repository.list_published_packages()
    return PackageListResponse(
        packages=[package_summary_from_package(package) for package in packages],
    )


async def get_package(package_id: str, db: AsyncSession) -> PackageSummary:
    """返回一个已发布剧本包，否则抛出 PACKAGE_NOT_FOUND。"""

    repository = PackageRepository(db)
    package = await repository.get_published_package(package_id)
    if package is None:
        raise not_found("PACKAGE_NOT_FOUND", "未找到指定剧本包")
    return package_summary_from_package(package)


async def list_playable_characters(
    package_id: str,
    db: AsyncSession,
) -> PackagePlayableCharactersResponse:
    """返回已发布剧本可公开展示的全部可玩角色。"""

    repository = PackageRepository(db)
    package = await repository.get_published_package(package_id)
    if package is None:
        raise not_found("PACKAGE_NOT_FOUND", "未找到指定剧本包")
    characters = await repository.list_playable_characters(package_id)
    return PackagePlayableCharactersResponse(
        characters=[playable_character_summary(character) for character in characters],
    )


# ── 剧本包状态服务 ──


async def update_package(
    package_id: str,
    payload: PackageUpdateRequest,
    db: AsyncSession,
) -> PackageUpdateResponse:
    """提交管理员发起的剧本包状态变更，否则抛出 PACKAGE_NOT_FOUND。"""

    repository = PackageRepository(db)
    if payload.status == "published":
        package = await get_runtime_package(
            db,
            package_id,
            for_update=True,
            published_only=False,
        )
        if package is None:
            raise not_found("PACKAGE_NOT_FOUND", "未找到指定剧本包")
        if "multiplayer" in package.package.config:
            playability = multiplayer_package_playability(package)
            if not playability.playable:
                diagnostic = playability.diagnostics[0]
                raise unprocessable_entity(
                    "PACKAGE_NOT_MULTIPLAYER",
                    diagnostic.message,
                    diagnostic.details(),
                )
    status = await repository.update_package_status(package_id, payload.status)
    if status is None:
        raise not_found("PACKAGE_NOT_FOUND", "未找到指定剧本包")
    return package_update_response_from_status(status)


# ── 数据库行到 API 响应 ──


def package_summary_from_package(package: StoredPackage) -> PackageSummary:
    """将已存储剧本包配置投影为面向玩家的 API 摘要。"""

    config = package.config
    return PackageSummary(
        id=package.id,
        title=package.name,
        description=config.info.description,
        poster_url=config.visual.poster or "",
        difficulty=config.info.difficulty,
        duration_minutes=config.info.duration_minutes,
        genre=config.info.genre,
        status=package.status,
        player_count=config.info.max_players,
    )


def playable_character_summary(
    character: StoredPlayableCharacter,
) -> PlayableCharacterSummary:
    """仅从角色定义中提取选角前允许公开的字段。"""

    definition = character.definition
    identity = _mapping(definition.get("identity"))
    personality = _mapping(definition.get("personality"))
    background = _text(identity.get("public")) or _text(definition.get("bio"))
    return PlayableCharacterSummary(
        id=character.id,
        name=character.name,
        portrait_url=_public_portrait_url(definition.get("portrait")),
        tagline="",
        personality=_text(personality.get("summary")),
        background=background,
    )


def _public_portrait_url(value: object) -> str:
    """只返回浏览器可读取的公开头像路径，不暴露私有存储定位符。"""

    portrait = _text(value)
    if portrait.startswith("/") or portrait.startswith("https://"):
        return portrait
    return ""


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if isinstance(key, str):
            result[key] = item
    return result


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def package_update_response_from_status(
    package: StoredPackageStatus,
) -> PackageUpdateResponse:
    """将已提交剧本包状态投影为更新响应结构。"""

    return PackageUpdateResponse(
        package_id=package.id,
        status=package.status,
        published_at=timestamp(package.updated_at),
    )
