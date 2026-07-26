import os
import re
from pathlib import Path

import pytest
from sqlalchemy import UniqueConstraint, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from engine.db.session import build_async_database_url, build_connect_args
from engine.db.tables import session_checkpoints

DATABASE_PRIVILEGE_URL_ENV = "AISCRIPTKILL_DATABASE_PRIVILEGE_DB_URL"
PROTECTED_TABLES = {
    "chat_messages",
    "final_submissions",
    "game_sessions",
    "reviews",
    "script_characters",
    "script_clues",
    "script_dm_guides",
    "script_endings",
    "script_evidences",
    "script_knowledge",
    "script_media",
    "script_scenes",
    "script_stages",
    "session_checkpoints",
    "session_discoveries",
}
MULTIPLAYER_PROTECTED_TABLES = {
    "room_character_assignments",
    "room_invites",
    "room_members",
    "room_principal_reservations",
    "room_required_members",
    "room_outbox",
    "session_command_identities",
    "session_command_receipts",
    "session_events",
}
DATABASE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
)
OBSOLETE_PLAYER_POLICIES = {
    "public_see_published_packages",
    "players_own_sessions",
    "players_see_open_scenes",
    "players_see_own_checkpoints",
    "players_see_own_discoveries",
    "players_see_own_messages",
    "players_see_own_reviews",
    "players_see_own_submissions",
    "players_see_unlocked_clues",
    "players_see_visible_evidences",
}


def test_fastapi_database_access_boundary_migration_contract() -> None:
    # 给定：最新迁移定义了唯一受支持的数据库访问边界。
    migration_paths = sorted(
        (Path(__file__).resolve().parents[2] / "supabase" / "migrations").glob(
            "*_fastapi_data_access_boundary.sql"
        )
    )
    assert len(migration_paths) == 1

    # 当：检查其中的 SQL 语句和面向运维人员的注释。
    sql = migration_paths[0].read_text(encoding="utf-8")
    without_comments = re.sub(r"--[^\n]*", "", sql)
    statements = {
        " ".join(statement.lower().split())
        for statement in without_comments.split(";")
        if statement.strip()
    }
    revoked_tables = _tables_for_role_statement(statements, "revoke", "anon, authenticated")
    client_grants = {
        statement
        for statement in statements
        if statement.startswith("grant ")
        and re.search(r"\bto\b.*\b(?:anon|authenticated)\b", statement) is not None
    }
    service_role_grants = {
        statement
        for statement in statements
        if statement.startswith("grant ")
        and re.search(r"\bto\b.*\bservice_role\b", statement) is not None
    }
    service_role_revokes = {
        statement
        for statement in statements
        if statement.startswith("revoke ")
        and re.search(r"\bfrom\b.*\bservice_role\b", statement) is not None
    }
    dropped_policies = {
        match.group("policy")
        for statement in statements
        if (
            match := re.fullmatch(
                r'drop policy if exists "(?P<policy>[^"]+)" on public\.[a-z_]+',
                statement,
            )
        )
    }

    # 则：浏览器角色无法绕过 FastAPI 目录投影访问基础表。
    assert revoked_tables == PROTECTED_TABLES | {"script_packages"}
    assert client_grants == set()
    assert service_role_grants == set()
    assert service_role_revokes == set()
    assert dropped_policies == OBSOLETE_PLAYER_POLICIES
    assert not any(
        statement.startswith("drop policy ") and '"service_role_full_access"' in statement
        for statement in statements
    )


def test_character_chapter_tables_have_service_role_only_access() -> None:
    migration_root = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    migrations = (
        migration_root / "20260713000000_character_chapters.sql",
        migration_root / "20260713010000_character_chapter_discoveries.sql",
    )

    for migration in migrations:
        sql = " ".join(migration.read_text(encoding="utf-8").lower().split())
        assert "revoke all privileges on table public." in sql
        assert "from anon, authenticated" in sql
        assert "grant all privileges on table public." in sql
        assert "to service_role" in sql

    discoveries = migrations[1].read_text(encoding="utf-8").lower()
    assert "'character_chapter'" in discoveries
    assert "drop constraint if exists session_discoveries_entity_type_check" in discoveries


def test_checkpoint_pending_writes_table_has_no_browser_role_access() -> None:
    # 给定：待处理写入可能先于检查点，因此使用专用迁移。
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260711143000_checkpoint_pending_writes.sql"
    )

    # 当：归一化迁移中的访问控制语句。
    sql = " ".join(migration.read_text(encoding="utf-8").lower().split())

    # 则：只有后端服务角色可以访问该进程恢复状态。
    assert "alter table public.session_checkpoint_writes enable row level security" in sql
    assert 'create policy "service_role_full_access"' in sql
    assert "grant all privileges on table public.session_checkpoint_writes to service_role" in sql
    assert (
        "revoke all privileges on table public.session_checkpoint_writes from anon, authenticated"
        in sql
    )


def test_room_outbox_table_has_no_browser_role_access() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "20260720020000_mp3_room_outbox.sql"
    )
    sql = " ".join(migration.read_text(encoding="utf-8").lower().split())

    assert "alter table public.room_outbox enable row level security" in sql
    assert 'create policy "service_role_full_access" on public.room_outbox' in sql
    assert "revoke all privileges on table public.room_outbox from anon, authenticated" in sql
    assert "grant all privileges on table public.room_outbox to service_role" in sql


def test_checkpoint_metadata_matches_database_idempotency_key() -> None:
    # 给定：保存器按会话和逻辑检查点 ID 执行更新插入。
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in session_checkpoints.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    # 则：SQLAlchemy metadata 与数据库迁移使用相同的幂等键。
    assert unique_constraints["uq_session_checkpoints_session_thread_ts"] == (
        "session_id",
        "thread_ts",
    )


def test_checkpoint_comment_fix_is_a_forward_migration() -> None:
    # 给定：旧数据字典已经可能部署，不能原地重写迁移历史。
    migration_root = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    original_comments = (migration_root / "007_schema_comments.sql").read_text(encoding="utf-8")
    forward_comments = (migration_root / "20260711150000_checkpoint_column_comments.sql").read_text(
        encoding="utf-8"
    )

    # 则：前向迁移明确修正三个字段，而旧迁移仍保留原始内容。
    assert "LangGraph 检查点时间戳" in original_comments
    assert "检查点完整 GameState" in original_comments
    assert "逻辑检查点 ID" in forward_comments
    assert "父级 LangGraph 逻辑检查点 ID" in forward_comments
    assert "版本化检查点信封" in forward_comments


@pytest.mark.skipif(
    os.getenv(DATABASE_PRIVILEGE_URL_ENV) is None,
    reason=f"需要通过 {DATABASE_PRIVILEGE_URL_ENV} 提供已应用全部迁移的可丢弃 PostgreSQL",
)
async def test_browser_roles_have_no_effective_access_to_protected_tables() -> None:
    # 给定：使用管理员连接访问已应用全部迁移的真实 PostgreSQL。
    database_url = os.environ[DATABASE_PRIVILEGE_URL_ENV]
    engine = create_async_engine(
        build_async_database_url(database_url),
        connect_args=build_connect_args(database_url),
    )
    restricted_tables = (
        PROTECTED_TABLES
        | MULTIPLAYER_PROTECTED_TABLES
        | {
            "script_packages",
            "session_checkpoint_writes",
        }
    )
    try:
        async with engine.connect() as connection:
            # 当：查询角色经继承和 PUBLIC 权限计算后的最终表权限。
            for role_name in ("anon", "authenticated"):
                for table_name in sorted(restricted_tables):
                    for privilege_name in DATABASE_PRIVILEGES:
                        granted = await connection.scalar(
                            text(
                                "SELECT has_table_privilege("
                                ":role_name, :table_name, :privilege_name)"
                            ),
                            {
                                "role_name": role_name,
                                "table_name": f"public.{table_name}",
                                "privilege_name": privilege_name,
                            },
                        )
                        assert granted is False, (
                            f"{role_name} 不应拥有 public.{table_name} 的 {privilege_name} 权限"
                        )
            await connection.rollback()

            # 则：每张受保护表都在独立事务中执行角色切换和真实拒绝探针。
            for role_name in ("anon", "authenticated"):
                for table_name in sorted(restricted_tables):
                    transaction = await connection.begin()
                    try:
                        await connection.exec_driver_sql(f"SET LOCAL ROLE {role_name}")
                        current_role = await connection.scalar(text("SELECT current_role"))
                        assert current_role == role_name
                        with pytest.raises(DBAPIError):
                            await connection.exec_driver_sql(
                                f"SELECT * FROM public.{table_name} LIMIT 0"
                            )
                    finally:
                        await transaction.rollback()
    finally:
        await engine.dispose()


def _tables_for_role_statement(
    statements: set[str],
    command: str,
    role_clause: str,
) -> set[str]:
    matching_tables: set[str] = set()
    pattern = re.compile(
        rf"{command} (?:all privileges|select) on table (?P<tables>.+) "
        + rf"(?:from|to) {role_clause}"
    )
    for statement in statements:
        match = pattern.fullmatch(statement)
        if match is not None:
            matching_tables.update(re.findall(r"public\.([a-z_]+)", match.group("tables")))
    return matching_tables
