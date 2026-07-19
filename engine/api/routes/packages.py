"""公开需要认证的剧本包导入端点。"""

from fastapi import APIRouter, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHttpException

from engine.api.errors import bad_request
from engine.api.middleware.auth import AdminUserDep, CurrentUserDep
from engine.api.schemas import (
    PackageImportResponse,
    PackageListResponse,
    PackagePlayableCharactersResponse,
    PackageUpdateRequest,
    PackageUpdateResponse,
)
from engine.api.schemas.packages import PackageSummary
from engine.core.package_archive import MAX_PACKAGE_UPLOAD_BYTES
from engine.db.session import SessionDep
from engine.services.import_service import (
    PackageUpload,
)
from engine.services.import_service import (
    import_package as import_package_service,
)
from engine.services.package_service import (
    get_package as get_package_service,
)
from engine.services.package_service import (
    list_packages as list_package_service,
)
from engine.services.package_service import (
    list_playable_characters as list_playable_characters_service,
)
from engine.services.package_service import (
    update_package as update_package_service,
)

# ── 剧本包管理路由 ──

router = APIRouter(prefix="/packages", tags=["packages"])


# ── 导入与发布状态 ──


@router.post(
    "",
    response_model=PackageImportResponse,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {"type": "string", "format": "binary"},
                        },
                    },
                },
            },
        },
    },
)
async def import_package(
    request: Request,
    _admin_user: AdminUserDep,
    db: SessionDep,
    publish: bool = False,
) -> PackageImportResponse:
    """以管理员身份校验并导入剧本包归档。

    Args:
        request: 包含一个 `file` 部件的已认证 multipart 请求。
        _admin_user: 要求已验证 Supabase 管理员用户的鉴权依赖。
        db: 请求作用域的异步数据库会话。
        publish: 是否立即发布导入的剧本包。

    Returns:
        已导入剧本包的标识、状态和校验报告。

    Raises:
        ApiError: 授权失败时抛出 `INVALID_TOKEN`、`AUTH_REQUIRED` 或
            `ADMIN_REQUIRED`；归档无法导入时抛出 `EMPTY_PACKAGE_UPLOAD`、
            `PACKAGE_UPLOAD_TOO_LARGE`、`PACKAGE_UPLOAD_INVALID` 或剧本包校验错误码。
    """
    file = await _package_file(request)
    try:
        content = await file.read(MAX_PACKAGE_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_PACKAGE_UPLOAD_BYTES:
        raise bad_request(
            "PACKAGE_UPLOAD_TOO_LARGE",
            f"上传的剧本包不能超过 {MAX_PACKAGE_UPLOAD_BYTES} 字节",
        )
    return await import_package_service(
        PackageUpload(
            filename=file.filename or "script-package.zip",
            content=content,
            publish=publish,
        ),
        db,
    )


async def _package_file(request: Request) -> UploadFile:
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise bad_request("PACKAGE_UPLOAD_INVALID", "剧本包上传必须使用 multipart/form-data")
    try:
        form = await request.form(max_files=1, max_fields=0)
    except StarletteHttpException as exc:
        raise bad_request("PACKAGE_UPLOAD_INVALID", "剧本包上传表单无效") from exc
    files = form.getlist("file")
    if len(files) != 1 or not isinstance(files[0], UploadFile):
        await form.close()
        raise bad_request("PACKAGE_UPLOAD_INVALID", "剧本包上传必须包含唯一的 file 文件")
    return files[0]


@router.patch("/{package_id}", response_model=PackageUpdateResponse)
async def update_package(
    package_id: str,
    payload: PackageUpdateRequest,
    _admin_user: AdminUserDep,
    db: SessionDep,
) -> PackageUpdateResponse:
    """以管理员身份更新已导入剧本包的状态。

    Args:
        package_id: 待更新剧本包的稳定标识符。
        payload: 请求的草稿、已发布或已归档状态。
        _admin_user: 要求已验证 Supabase 管理员用户的鉴权依赖。
        db: 请求作用域的异步数据库会话。

    Returns:
        剧本包标识符、更新后的状态和更新时间戳。

    Raises:
        ApiError: 授权失败时抛出 `INVALID_TOKEN`、`AUTH_REQUIRED` 或
            `ADMIN_REQUIRED`；没有匹配剧本包时抛出 `PACKAGE_NOT_FOUND`。
    """
    return await update_package_service(package_id, payload, db)


# ── 前端剧本库查询 ──


@router.get("", response_model=PackageListResponse)
async def list_packages(
    _current_user: CurrentUserDep,
    db: SessionDep,
) -> PackageListResponse:
    """列出前端剧本库可见的已发布剧本包。

    Args:
        _current_user: 由鉴权依赖解析的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        按仓储查询顺序排列的已发布剧本包摘要。

    Raises:
        ApiError: 提供的 Bearer Token 无效时抛出 `INVALID_TOKEN`。
    """
    return await list_package_service(db)


@router.get("/{package_id}", response_model=PackageSummary)
async def get_package(
    package_id: str,
    _current_user: CurrentUserDep,
    db: SessionDep,
) -> PackageSummary:
    """为前端详情页返回一个已发布剧本包。

    Args:
        package_id: 待读取已发布剧本包的稳定标识符。
        _current_user: 由鉴权依赖解析的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        已发布剧本包的元数据和面向玩家的配置。

    Raises:
        ApiError: Bearer 鉴权无效时抛出 `INVALID_TOKEN`；剧本包缺失或未发布时抛出
            `PACKAGE_NOT_FOUND`。
    """
    return await get_package_service(package_id, db)


@router.get(
    "/{package_id}/characters",
    response_model=PackagePlayableCharactersResponse,
)
async def list_playable_characters(
    package_id: str,
    _current_user: CurrentUserDep,
    db: SessionDep,
) -> PackagePlayableCharactersResponse:
    """返回剧本在选角阶段公开的全部可玩角色。

    Args:
        package_id: 待读取可玩角色的已发布剧本包标识符。
        _current_user: 由鉴权依赖解析的可选 Supabase 身份。
        db: 请求作用域的异步数据库会话。

    Returns:
        按剧本声明顺序排列且过滤过剧透字段的可玩角色列表。

    Raises:
        ApiError: Bearer 鉴权无效时抛出 `INVALID_TOKEN`；剧本缺失或未发布时抛出
            `PACKAGE_NOT_FOUND`。
    """
    return await list_playable_characters_service(package_id, db)
