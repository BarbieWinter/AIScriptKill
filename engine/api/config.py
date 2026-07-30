"""加载并校验不可变的 API 运行时配置。"""

from functools import lru_cache
from pathlib import Path
from typing import ClassVar, Final, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# ── 配置来源 ──

DEFAULT_CORS_ORIGINS: Final[str] = "http://localhost:3000,http://127.0.0.1:3000"
ENV_PATH: Final[Path] = Path(__file__).resolve().parents[2] / ".env"
LOCAL_SUPABASE_URL: Final[str] = "http://127.0.0.1:54321"
LOCAL_DATABASE_URL: Final[str] = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"


# ── 后端运行配置 ──


class Settings(BaseSettings):
    """校验 API、数据库、鉴权和 RAG 适配器使用的环境配置。"""

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
    supabase_storage_bucket: str = Field(
        default="script-assets",
        alias="SUPABASE_STORAGE_BUCKET",
        description="Supabase Storage bucket for imported package assets.",
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
        default=360,
        alias="RATE_LIMIT_PER_MINUTE",
        ge=1,
        description="Per-client request limit for the API gateway skeleton.",
    )
    multiplayer_v1: bool = Field(
        default=False,
        alias="MULTIPLAYER_V1",
        description="Enable the MP-2 room lobby routes and browser entry flow.",
    )
    room_events_v1: bool = Field(
        default=False,
        alias="ROOM_EVENTS_V1",
        description="Enable the independently supervised room-event relay and stream runtime.",
    )
    room_event_relay_batch_size: int = Field(
        default=100,
        alias="ROOM_EVENT_RELAY_BATCH_SIZE",
        ge=1,
        le=1000,
        description="Maximum outbox rows claimed by one relay cycle.",
    )
    room_event_relay_poll_seconds: float = Field(
        default=0.5,
        alias="ROOM_EVENT_RELAY_POLL_SECONDS",
        ge=0.05,
        le=60.0,
        description="Idle delay between relay claim cycles.",
    )
    room_event_relay_lease_seconds: int = Field(
        default=30,
        alias="ROOM_EVENT_RELAY_LEASE_SECONDS",
        ge=5,
        le=600,
        description="Exclusive delivery lease duration before restart recovery may reclaim a row.",
    )
    room_event_relay_publish_timeout_seconds: float = Field(
        default=5.0,
        alias="ROOM_EVENT_RELAY_PUBLISH_TIMEOUT_SECONDS",
        ge=0.1,
        le=120.0,
        description="Maximum transport wait for one event before recording a failed attempt.",
    )
    room_event_relay_retry_base_seconds: int = Field(
        default=1,
        alias="ROOM_EVENT_RELAY_RETRY_BASE_SECONDS",
        ge=1,
        le=300,
        description="Initial relay retry delay before exponential capped backoff.",
    )
    room_event_relay_retry_max_seconds: int = Field(
        default=60,
        alias="ROOM_EVENT_RELAY_RETRY_MAX_SECONDS",
        ge=1,
        le=3600,
        description="Maximum relay retry delay.",
    )
    room_event_relay_max_attempts: int = Field(
        default=5,
        alias="ROOM_EVENT_RELAY_MAX_ATTEMPTS",
        ge=1,
        le=100,
        description="Delivery attempts before an event enters poison quarantine.",
    )
    room_event_relay_shutdown_grace_seconds: float = Field(
        default=10.0,
        alias="ROOM_EVENT_RELAY_SHUTDOWN_GRACE_SECONDS",
        ge=1.0,
        le=120.0,
        description="Maximum graceful relay shutdown wait before task cancellation.",
    )
    room_event_notify_channel: str = Field(
        default="aiscriptkill_room_events_v1",
        alias="ROOM_EVENT_NOTIFY_CHANNEL",
        pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,62}$",
        description="PostgreSQL notification channel carrying bounded public event references.",
    )
    ai_dm_v1: bool = Field(
        default=False,
        alias="AI_DM_V1",
        description="Reserved MP-0 AI-DM rollout flag; it does not enable an entry point.",
    )
    rag_embedding_provider: Literal["deterministic", "dashscope"] = Field(
        default="deterministic",
        alias="RAG_EMBEDDING_PROVIDER",
        description="Embedding backend for script_knowledge indexing.",
    )
    rag_embedding_dimensions: int = Field(
        default=1024,
        alias="RAG_EMBEDDING_DIMENSIONS",
        ge=1024,
        le=1024,
        description="Fixed text-embedding-v4 dimensions stored in script_knowledge.embedding.",
    )
    rag_dashscope_embedding_model: Literal["text-embedding-v4"] = Field(
        default="text-embedding-v4",
        alias="RAG_DASHSCOPE_EMBEDDING_MODEL",
        description="DashScope embedding model used for production script indexing.",
    )
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        alias="DASHSCOPE_BASE_URL",
        description="DashScope OpenAI-compatible API base URL.",
    )
    dashscope_api_key: str | None = Field(
        default=None,
        alias="DASHSCOPE_API_KEY",
        description="Server-side DashScope API key.",
        repr=False,
    )
    npc_generation_provider: Literal["deterministic", "openai_compatible"] = Field(
        default="openai_compatible",
        alias="NPC_GENERATION_PROVIDER",
        description="NPC dialogue generation backend.",
    )
    openai_api_key: SecretStr | None = Field(
        default=None,
        alias="OPENAI_API_KEY",
        description="Server-side API key for the OpenAI-compatible NPC endpoint.",
        repr=False,
    )
    openai_base_url: str | None = Field(
        default=None,
        alias="OPENAI_BASE_URL",
        description="Base URL for an OpenAI-compatible API, including its version path.",
    )
    openai_model: str | None = Field(
        default=None,
        alias="OPENAI_MODEL",
        min_length=1,
        max_length=256,
        description="Model identifier accepted by the configured OpenAI-compatible API.",
    )
    npc_openai_max_tokens: int = Field(
        default=512,
        alias="NPC_OPENAI_MAX_TOKENS",
        ge=64,
        le=2048,
        description="Maximum completion tokens for one compatible NPC reply.",
    )
    npc_openai_timeout_seconds: float = Field(
        default=20.0,
        alias="NPC_OPENAI_TIMEOUT_SECONDS",
        ge=1.0,
        le=60.0,
        description="OpenAI-compatible request timeout for one NPC reply.",
    )
    supabase_jwt_audience: str = Field(
        default="authenticated",
        alias="SUPABASE_JWT_AUDIENCE",
        min_length=1,
        max_length=128,
        description="Expected audience for Supabase access tokens.",
    )

    # 前端跨域配置：支持 `.env.example` 中用逗号分隔多个 Origin
    @property
    def cors_origins(self) -> list[str]:
        """从逗号分隔的配置中返回规范化的非空来源。"""

        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    # 数据库连接优先级：服务运行优先走 Supabase Pooler，缺失时回退 Direct URI
    @property
    def effective_database_url(self) -> str:
        """优先返回运行时连接池 URL，缺失时回退到数据库直连 URL。"""

        return self.database_pooler_url or self.database_url


# ── 单例配置入口 ──


@lru_cache
def get_settings() -> Settings:
    """返回进程级缓存且已通过校验的配置实例。"""

    return Settings()
