"""构建 FastAPI 应用及其进程生命周期。"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.api.config import get_settings
from engine.api.errors import (
    DATABASE_EXCEPTION_TYPES,
    ApiError,
    api_exception_handler,
    database_exception_handler,
)
from engine.api.middleware.body_limit import RequestBodyLimitMiddleware
from engine.api.middleware.rate_limit import RateLimitMiddleware
from engine.api.routes import actions, packages, sessions
from engine.api.websocket.handler import router as websocket_router
from engine.db.session import check_database_connection, dispose_engine

# ── 应用生命周期 ──


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    """将控制权交给 FastAPI，并在关闭时释放连接池。"""

    try:
        yield
    finally:
        await dispose_engine()


# ── FastAPI 应用装配 ──


def create_app() -> FastAPI:
    """装配中间件、异常处理器、路由和健康检查端点。"""

    settings = get_settings()
    api = FastAPI(
        title="AI Script Kill Engine",
        version="0.1.0",
        description="AI 沉浸式悬疑互动剧游戏引擎 API",
        lifespan=lifespan,
    )
    api.add_exception_handler(ApiError, api_exception_handler)
    for exception_type in DATABASE_EXCEPTION_TYPES:
        api.add_exception_handler(exception_type, database_exception_handler)
    api.add_middleware(RequestBodyLimitMiddleware)
    api.add_middleware(
        RateLimitMiddleware,
        limit_per_minute=settings.rate_limit_per_minute,
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    api.include_router(sessions.router, prefix="/api/v1")
    api.include_router(sessions.invite_router, prefix="/api/v1")
    api.include_router(actions.router, prefix="/api/v1")
    api.include_router(packages.router, prefix="/api/v1")
    api.include_router(websocket_router, prefix="/api/v1")
    api.add_api_route("/health", health, methods=["GET"])
    api.add_api_route("/health/db", database_health, methods=["GET"])

    return api


# ── 基础健康检查 ──


async def health() -> dict[str, str]:
    """返回无需数据库连接的进程健康状态。"""

    return {"status": "ok", "engine": "aiscriptkill", "version": "0.1.0"}


async def database_health() -> dict[str, str]:
    """校验数据库连通性和必要表后返回健康状态。"""

    await check_database_connection()
    return {"status": "ok", "database": "reachable"}


app = create_app()
