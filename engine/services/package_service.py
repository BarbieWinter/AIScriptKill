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
    repository = PackageRepository(db)
    packages = await repository.list_published_packages()
    return PackageListResponse(
        packages=[package_summary_from_package(package) for package in packages],
    )


async def get_package(package_id: str, db: AsyncSession) -> PackageSummary:
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
    repository = PackageRepository(db)
    status = await repository.update_package_status(package_id, payload.status)
    if status is None:
        raise not_found("PACKAGE_NOT_FOUND", "未找到指定剧本包")
    return package_update_response_from_status(status)


# ── 数据库行到 API 响应 ──


def package_summary_from_package(package: StoredPackage) -> PackageSummary:
    config = package.config
    return PackageSummary(
        id=package.id,
        title=package.name,
        description=config.description,
        poster_url=config.poster_url,
        difficulty=config.difficulty,
        duration_minutes=config.duration_minutes,
        genre=config.genre,
        status=package.status,
        player_count=config.player_count,
    )


def package_update_response_from_status(
    package: StoredPackageStatus,
) -> PackageUpdateResponse:
    return PackageUpdateResponse(
        package_id=package.id,
        status=package.status,
        published_at=timestamp(package.updated_at),
    )
