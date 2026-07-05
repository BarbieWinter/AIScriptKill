from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Final, cast

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 配置来源 ──

DEFAULT_CORS_ORIGINS: Final[str] = "http://localhost:3000,http://127.0.0.1:3000"
ENV_EXAMPLE_PATH: Final[Path] = Path(__file__).resolve().parents[2] / ".env.example"


# ── 后端运行配置 ──


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_EXAMPLE_PATH,
        extra="ignore",
        populate_by_name=True,
    )

    # Supabase 项目信息：直接来自项目根目录 `.env.example`
    supabase_project_ref: str | None = Field(
        default=None,
        alias="SUPABASE_PROJECT_REF",
        description="Supabase project ref for CLI linking and diagnostics.",
    )
    supabase_url: str = Field(
        alias="SUPABASE_URL",
        description="Supabase project REST URL.",
    )
    supabase_publishable_key: str = Field(
        alias="SUPABASE_PUBLISHABLE_KEY",
        description="Public Supabase key used for anon/client-side access.",
    )
    supabase_secret_key: str = Field(
        alias="SUPABASE_SECRET_KEY",
        description="Server-side Supabase secret key.",
    )
    database_url: str = Field(
        alias="DATABASE_URL",
        description="Postgres connection string for server-side migrations/services.",
    )
    cors_origins_raw: str = Field(
        default=DEFAULT_CORS_ORIGINS,
        alias="CORS_ORIGINS",
        description="Comma-separated frontend origins allowed by CORS.",
    )
    rate_limit_per_minute: int = Field(
        default=120,
        alias="RATE_LIMIT_PER_MINUTE",
        ge=1,
        description="Per-client request limit for the API gateway skeleton.",
    )

    # 前端跨域配置：支持 `.env.example` 中用逗号分隔多个 Origin
    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]


# ── 单例配置入口 ──


@lru_cache
def get_settings() -> Settings:
    settings_factory = cast(Callable[[], Settings], Settings)
    return settings_factory()
