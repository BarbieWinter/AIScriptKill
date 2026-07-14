"""创建数据库会话并校验预期的运行时结构。"""

from collections.abc import AsyncGenerator
from typing import Annotated, Final
from urllib.parse import urlparse

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from engine.api.config import get_settings
from engine.api.errors import DatabaseSchemaError

# ── 连接 URL 规范化 ──

ASYNC_POSTGRES_SCHEME: Final[str] = "postgresql+asyncpg://"
SYNC_POSTGRES_SCHEME: Final[str] = "postgresql://"
LOCAL_DATABASE_HOSTS: Final[frozenset[str]] = frozenset({"127.0.0.1", "localhost"})


def build_async_database_url(database_url: str) -> str:
    """将同步 PostgreSQL URL 转换为 asyncpg SQLAlchemy 协议。"""

    if database_url.startswith(ASYNC_POSTGRES_SCHEME):
        return database_url
    if database_url.startswith(SYNC_POSTGRES_SCHEME):
        return f"{ASYNC_POSTGRES_SCHEME}{database_url.removeprefix(SYNC_POSTGRES_SCHEME)}"
    return database_url


def build_connect_args(database_url: str) -> dict[str, int | str]:
    """构建 asyncpg 参数，并要求已知本地主机以外的连接使用 TLS。"""

    connect_args: dict[str, int | str] = {"statement_cache_size": 0}
    if urlparse(database_url).hostname not in LOCAL_DATABASE_HOSTS:
        connect_args["ssl"] = "require"
    return connect_args


# ── SQLAlchemy 异步引擎 ──


def create_engine() -> AsyncEngine:
    """根据已校验运行时配置创建进程级异步引擎。"""

    settings = get_settings()
    database_url = settings.effective_database_url
    return create_async_engine(
        build_async_database_url(database_url),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args=build_connect_args(database_url),
    )


engine = create_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# ── FastAPI 数据库会话依赖 ──


async def get_db_session() -> AsyncGenerator[AsyncSession]:
    """提供请求作用域会话，并回滚所有未完成事务。"""

    async with SessionFactory() as session:
        try:
            yield session
        finally:
            if session.in_transaction():
                await session.rollback()


SessionDep = Annotated[AsyncSession, Depends(get_db_session)]


# ── 数据库连通性检查 ──

REQUIRED_PUBLIC_TABLES: Final[tuple[str, ...]] = (
    "script_packages",
    "script_stages",
    "script_characters",
    "script_character_chapters",
    "script_clues",
    "script_evidences",
    "script_scenes",
    "script_media",
    "script_knowledge",
    "game_sessions",
    "session_checkpoints",
    "session_checkpoint_writes",
    "chat_messages",
    "session_discoveries",
    "final_submissions",
    "reviews",
)


async def check_database_connection() -> None:
    """校验连通性，并在缺少表时抛出 DatabaseSchemaError。"""

    async with engine.connect() as connection:
        await connection.execute(text("select 1"))
        existing_tables = await existing_public_tables(connection)
    missing_tables = missing_required_tables(existing_tables)
    if len(missing_tables) > 0:
        raise DatabaseSchemaError(missing_tables)


async def existing_public_tables(connection: AsyncConnection) -> frozenset[str]:
    """返回 public schema 中实际存在的已配置必要表。"""

    tables: set[str] = set()
    for table_name in REQUIRED_PUBLIC_TABLES:
        result = await connection.execute(
            text("select to_regclass(:qualified_table)"),
            {"qualified_table": f"public.{table_name}"},
        )
        if result.scalar_one_or_none() is not None:
            tables.add(table_name)
    return frozenset(tables)


def missing_required_tables(existing_tables: frozenset[str]) -> tuple[str, ...]:
    """返回数据库内省结果中缺失的必要表名。"""

    return tuple(
        table_name for table_name in REQUIRED_PUBLIC_TABLES if table_name not in existing_tables
    )


# ── 应用关闭清理 ──


async def dispose_engine() -> None:
    """在应用关闭时断开连接池中的全部数据库连接。"""

    await engine.dispose()
