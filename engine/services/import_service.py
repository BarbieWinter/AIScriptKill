from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from engine.api.errors import bad_request
from engine.api.schemas import PackageImportResponse
from engine.api.schemas.packages import ValidationReport
from engine.core.package_importer import import_to_db
from engine.core.package_loader import PackageArchiveError, load_package_archive
from engine.core.package_storage import create_package_asset_storage

# ── 剧本包导入输入 ──


@dataclass(frozen=True, slots=True)
class PackageUpload:
    filename: str
    content: bytes
    publish: bool


# ── 剧本包导入服务 ──


async def import_package(
    upload: PackageUpload,
    db: AsyncSession,
) -> PackageImportResponse:
    if len(upload.content) == 0:
        raise bad_request("EMPTY_PACKAGE_UPLOAD", "上传的剧本包为空")
    try:
        package = load_package_archive(upload.content, upload.publish)
    except PackageArchiveError as exc:
        raise bad_request(exc.code, exc.message) from exc

    package = await import_to_db(package, db, create_package_asset_storage())
    return PackageImportResponse(
        package_id=package.package.id,
        title=package.package.title,
        status=package.package.status,
        validation=ValidationReport(
            valid=True,
            warnings=list(package.warnings),
            errors=[],
        ),
    )
