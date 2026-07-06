from dataclasses import dataclass
from http import HTTPStatus
from typing import ClassVar

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

# ── 统一错误响应模型 ──


class ErrorDetail(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error message.")
    details: dict[str, str] = Field(
        default_factory=dict,
        description="Optional structured details for debugging or UI hints.",
    )


class ErrorEnvelope(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    error: ErrorDetail = Field(description="Error payload.")


# ── API 边界异常 ──


class ApiError(Exception):
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
    missing_tables: tuple[str, ...]

    def __str__(self) -> str:
        return f"Missing Supabase tables: {', '.join(self.missing_tables)}"


# ── FastAPI 异常处理入口 ──


async def api_exception_handler(
    _: Request,
    exc: Exception,
) -> JSONResponse:
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
    match exc:
        case DatabaseSchemaError(missing_tables=missing_tables):
            return JSONResponse(
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                content=ErrorEnvelope(
                    error=ErrorDetail(
                        code="DATABASE_SCHEMA_INCOMPLETE",
                        message="Supabase 数据库迁移尚未完整应用。",
                        details={"missing_tables": ",".join(missing_tables)},
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
    return ApiError(
        status_code=HTTPStatus.UNAUTHORIZED,
        code=code,
        message=message,
    )


def forbidden(code: str, message: str) -> ApiError:
    return ApiError(
        status_code=HTTPStatus.FORBIDDEN,
        code=code,
        message=message,
    )


def bad_request(code: str, message: str) -> ApiError:
    return ApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code=code,
        message=message,
    )


def not_found(code: str, message: str) -> ApiError:
    return ApiError(
        status_code=HTTPStatus.NOT_FOUND,
        code=code,
        message=message,
    )


DATABASE_EXCEPTION_TYPES = (ConnectionError, DatabaseSchemaError, SQLAlchemyError)
