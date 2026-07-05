from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from engine.api.middleware.auth import CurrentUserDep
from engine.api.schemas import (
    PackageImportResponse,
    PackageListResponse,
    PackageUpdateRequest,
    PackageUpdateResponse,
)
from engine.services.import_service import (
    import_package_stub,
    list_packages_stub,
    update_package_stub,
)

# ── 剧本包管理路由 ──

router = APIRouter(prefix="/packages", tags=["packages"])


# ── 导入与发布状态 ──


@router.post("", response_model=PackageImportResponse)
async def import_package(
    file: Annotated[UploadFile, File(description="Zip archive of a script package.")],
    _current_user: CurrentUserDep,
    publish: bool = False,
) -> PackageImportResponse:
    """Import and validate a script package archive for the admin surface."""
    return import_package_stub(file.filename or "script-package.zip", publish)


@router.patch("/{package_id}", response_model=PackageUpdateResponse)
async def update_package(
    package_id: str,
    payload: PackageUpdateRequest,
    _current_user: CurrentUserDep,
) -> PackageUpdateResponse:
    """Update publication status for an imported script package."""
    return update_package_stub(package_id, payload)


# ── 前端剧本库查询 ──


@router.get("", response_model=PackageListResponse)
async def list_packages(_current_user: CurrentUserDep) -> PackageListResponse:
    """List published script packages for the frontend library."""
    return list_packages_stub()
