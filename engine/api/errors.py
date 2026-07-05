from http import HTTPStatus
from typing import ClassVar

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

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


# ── 常用错误工厂 ──


def unauthorized(code: str, message: str) -> ApiError:
    return ApiError(
        status_code=HTTPStatus.UNAUTHORIZED,
        code=code,
        message=message,
    )
