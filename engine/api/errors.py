"""定义稳定的 API 错误载荷及异常到响应的映射。"""

from dataclasses import dataclass
from http import HTTPStatus
from typing import ClassVar

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

# ── 统一错误响应模型 ──


class ErrorDetail(BaseModel):
    """描述 API 错误中供程序和用户读取的稳定信息。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, str] = Field(
        default_factory=dict,
        description="Optional structured details for debugging or UI hints.",
    )


class ErrorEnvelope(BaseModel):
    """将所有已处理的 API 错误统一封装在公开的 error 字段下。"""

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    error: ErrorDetail = Field(description="Error payload.")


# ── API 边界异常 ──


class ApiError(Exception):
    """将 HTTP 状态和可序列化错误详情传递到 API 边界。"""

    status_code: int
    error: ErrorDetail

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = ErrorDetail(
            code=code,
            message=message,
            details=details or {},
        )


@dataclass(frozen=True, slots=True)
class DatabaseSchemaError(Exception):
    """报告当前数据库中缺失的必要 public 表。"""

    missing_tables: tuple[str, ...]

    def __str__(self) -> str:
        return f"Missing Supabase tables: {', '.join(self.missing_tables)}"


# ── FastAPI 异常处理入口 ──


async def api_exception_handler(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    """序列化 ApiError，同时让未预期异常继续向上传播。"""

    if not isinstance(exc, ApiError):
        raise exc

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorEnvelope(error=exc.error).model_dump(mode="json"),
    )


async def database_exception_handler(
    _: Request,
    exc: Exception,
) -> JSONResponse:
    """将数据库不可用或结构不完整映射为稳定的 503 响应载荷。"""

    if isinstance(exc, DatabaseSchemaError):
        return JSONResponse(
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            content=ErrorEnvelope(
                error=ErrorDetail(
                    code="DATABASE_SCHEMA_INCOMPLETE",
                    message="Supabase 数据库迁移尚未完整应用。",
                    details={"missing_tables": ",".join(exc.missing_tables)},
                ),
            ).model_dump(mode="json"),
        )

    return JSONResponse(
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        content=ErrorEnvelope(
            error=ErrorDetail(
                code="DATABASE_UNAVAILABLE",
                message="数据库连接不可用，请检查 Supabase 连接配置。",
                details={"reason": exc.__class__.__name__},
            ),
        ).model_dump(mode="json"),
    )


# ── 常用错误工厂 ──


def unauthorized(code: str, message: str) -> ApiError:
    """使用调用方提供的稳定错误码构造 401 API 错误。"""

    return ApiError(
        status_code=HTTPStatus.UNAUTHORIZED,
        code=code,
        message=message,
    )


def forbidden(code: str, message: str) -> ApiError:
    """使用调用方提供的稳定错误码构造 403 API 错误。"""

    return ApiError(
        status_code=HTTPStatus.FORBIDDEN,
        code=code,
        message=message,
    )


def bad_request(code: str, message: str) -> ApiError:
    """使用调用方提供的稳定错误码构造 400 API 错误。"""

    return ApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code=code,
        message=message,
    )


def not_found(code: str, message: str) -> ApiError:
    """使用调用方提供的稳定错误码构造 404 API 错误。"""

    return ApiError(
        status_code=HTTPStatus.NOT_FOUND,
        code=code,
        message=message,
    )


DATABASE_EXCEPTION_TYPES = (ConnectionError, DatabaseSchemaError, SQLAlchemyError)
