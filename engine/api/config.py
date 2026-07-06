from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 配置来源 ──

DEFAULT_CORS_ORIGINS: Final[str] = "http://localhost:3000,http://127.0.0.1:3000"
ENV_PATH: Final[Path] = Path(__file__).resolve().parents[2] / ".env"
LOCAL_SUPABASE_URL: Final[str] = "http://127.0.0.1:54321"
LOCAL_DATABASE_URL: Final[str] = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


# ── 后端运行配置 ──


class Settings(BaseSettings):
    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=ENV_PATH,
        extra="ignore",
        populate_by_name=True,
    )

    supabase_project_ref: str | None = Field(
        default="local",
        alias="SUPABASE_PROJECT_REF",
        description="Supabase project ref for CLI linking and diagnostics.",
    )
    supabase_url: str = Field(
        default=LOCAL_SUPABASE_URL,
        alias="SUPABASE_URL",
        description="Supabase project REST URL.",
    )
    supabase_publishable_key: str = Field(
        default="local-publishable-key",
        alias="SUPABASE_PUBLISHABLE_KEY",
        description="Public Supabase key used for anon/client-side access.",
    )
    supabase_secret_key: str = Field(
        default="local-secret-key",
        alias="SUPABASE_SECRET_KEY",
        description="Server-side Supabase secret key.",
    )
    database_url: str = Field(
        default=LOCAL_DATABASE_URL,
        alias="DATABASE_URL",
        description="Postgres connection string for server-side migrations/services.",
    )
    database_pooler_url: str | None = Field(
        default=None,
        alias="DATABASE_POOLER_URL",
        description="Optional Supabase pooler connection string for runtime services.",
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

    # 数据库连接优先级：服务运行优先走 Supabase Pooler，缺失时回退 Direct URI
    @property
    def effective_database_url(self) -> str:
        return self.database_pooler_url or self.database_url


# ── 单例配置入口 ──


@lru_cache
def get_settings() -> Settings:
    return Settings(**{})
