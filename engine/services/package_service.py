"""协调剧本包校验、私有存储和持久化。"""

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import not_found
from engine.api.schemas import PackageListResponse
from engine.api.schemas.packages import (
    PackageSummary,
    PackageUpdateRequest,
    PackageUpdateResponse,
)
from engine.repositories.package_repository import (
    PackageRepository,
    StoredPackage,
    StoredPackageStatus,
)
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


# ── 剧本包状态服务 ──


async def update_package(
    package_id: str,
    payload: PackageUpdateRequest,
    db: AsyncSession,
) -> PackageUpdateResponse:
    """提交管理员发起的剧本包状态变更，否则抛出 PACKAGE_NOT_FOUND。"""

    repository = PackageRepository(db)
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


def package_update_response_from_status(
    package: StoredPackageStatus,
) -> PackageUpdateResponse:
    """将已提交剧本包状态投影为更新响应结构。"""

    return PackageUpdateResponse(
        package_id=package.id,
        status=package.status,
        published_at=timestamp(package.updated_at),
    )
