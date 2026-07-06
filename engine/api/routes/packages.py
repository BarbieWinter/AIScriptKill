from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from engine.api.middleware.auth import AdminUserDep, CurrentUserDep
from engine.api.schemas import (
    PackageImportResponse,
    PackageListResponse,
    PackageUpdateRequest,
    PackageUpdateResponse,
)
from engine.db.session import SessionDep
from engine.services.import_service import (
    PackageUpload,
)
from engine.services.import_service import (
    import_package as import_package_service,
)
from engine.services.package_service import (
    list_packages as list_package_service,
)
from engine.services.package_service import (
    update_package as update_package_service,
)

# ── 剧本包管理路由 ──

router = APIRouter(prefix="/packages", tags=["packages"])


# ── 导入与发布状态 ──


@router.post("", response_model=PackageImportResponse)
async def import_package(
    file: Annotated[UploadFile, File(description="Zip archive of a script package.")],
    _admin_user: AdminUserDep,
    db: SessionDep,
    publish: bool = False,
) -> PackageImportResponse:
    """Import and validate a script package archive for the admin surface."""
    content = await file.read()
    return await import_package_service(
        PackageUpload(
            filename=file.filename or "script-package.zip",
            content=content,
            publish=publish,
        ),
        db,
    )


@router.patch("/{package_id}", response_model=PackageUpdateResponse)
async def update_package(
    package_id: str,
    payload: PackageUpdateRequest,
    _admin_user: AdminUserDep,
    db: SessionDep,
) -> PackageUpdateResponse:
    """Update publication status for an imported script package."""
    return await update_package_service(package_id, payload, db)


# ── 前端剧本库查询 ──


@router.get("", response_model=PackageListResponse)
async def list_packages(
    _current_user: CurrentUserDep,
    db: SessionDep,
) -> PackageListResponse:
    """List published script packages for the frontend library."""
    return await list_package_service(db)
