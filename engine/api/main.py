from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.api.config import get_settings
from engine.api.errors import ApiError, api_exception_handler
from engine.api.middleware.rate_limit import RateLimitMiddleware
from engine.api.routes import actions, packages, sessions
from engine.api.websocket.handler import router as websocket_router

# ── 应用生命周期 ──


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    yield


# ── FastAPI 应用装配 ──


def create_app() -> FastAPI:
    settings = get_settings()
    api = FastAPI(
        title="AI Script Kill Engine",
        version="0.1.0",
        description="AI 沉浸式悬疑互动剧游戏引擎 API",
        lifespan=lifespan,
    )
    api.add_exception_handler(ApiError, api_exception_handler)
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
    api.include_router(actions.router, prefix="/api/v1")
    api.include_router(packages.router, prefix="/api/v1")
    api.include_router(websocket_router, prefix="/api/v1")
    api.add_api_route("/health", health, methods=["GET"])

    return api


# ── 基础健康检查 ──


async def health() -> dict[str, str]:
    return {"status": "ok", "engine": "aiscriptkill", "version": "0.1.0"}


app = create_app()
