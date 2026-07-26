import re
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from engine.db.session import REQUIRED_PUBLIC_TABLES
from engine.db.tables import (
    game_sessions,
    metadata,
    room_character_assignments,
    room_invites,
    room_members,
    room_principal_reservations,
    room_required_members,
)

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260718000000_multiplayer_rooms.sql"
)
FORWARD_PRESENCE_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260723010000_multiplayer_scene_presence.sql"
)
ROOM_TABLE_NAMES = {
    "room_members",
    "room_character_assignments",
    "room_invites",
    "room_required_members",
    "room_principal_reservations",
}


def test_multiplayer_migration_declares_mode_aware_legacy_constraints() -> None:
    sql = _normalized_sql()

    assert "add column mode text not null default 'legacy_single'" in sql
    assert "alter column player_character_id drop not null" in sql
    assert "drop constraint if exists game_sessions_status_check" in sql
    assert "mode = 'legacy_single'" in sql
    assert "status in ('in_progress', 'paused', 'completed', 'abandoned')" in sql
    assert "mode = 'multiplayer_v1'" in sql
    assert "status in ('lobby', 'active', 'completed', 'closed')" in sql
    assert "mode = 'legacy_single' and player_character_id is not null" in sql
    assert "mode = 'multiplayer_v1' and player_character_id is null" in sql


def test_multiplayer_sessions_pin_state_and_runtime_package_versions() -> None:
    sql = _normalized_sql()

    for fragment in (
        "add column revision bigint not null default 0",
        "add column event_head_sequence bigint not null default 0",
        "add column state_schema_version integer",
        "add column runtime_package_version text",
        "add column runtime_package_snapshot jsonb",
        "add column runtime_package_sha256 text",
        "add column started_at timestamptz",
        "add column closed_at timestamptz",
        "check (revision >= 0)",
        "check (event_head_sequence >= 0)",
        "state_schema_version = 2",
        "runtime_package_sha256 ~ '^[0-9a-f]{64}$'",
    ):
        assert fragment in sql

    assert isinstance(game_sessions.c.runtime_package_snapshot.type, JSONB)
    assert game_sessions.c.player_character_id.nullable is True
    assert game_sessions.c.mode.server_default is not None
    assert game_sessions.c.revision.server_default is not None
    assert game_sessions.c.event_head_sequence.server_default is not None


def test_room_tables_have_same_session_composite_integrity_and_concurrency_keys() -> None:
    assert ROOM_TABLE_NAMES <= set(metadata.tables)
    assert ROOM_TABLE_NAMES <= set(REQUIRED_PUBLIC_TABLES)

    assert tuple(room_character_assignments.primary_key.columns.keys()) == (
        "session_id",
        "member_id",
    )
    assert tuple(room_required_members.primary_key.columns.keys()) == (
        "session_id",
        "ordinal",
    )
    assert tuple(room_principal_reservations.primary_key.columns.keys()) == ("principal_id",)

    assert _unique_columns(room_members) >= {
        ("session_id", "principal_id"),
        ("id", "session_id"),
        ("id", "session_id", "principal_id"),
    }
    assert _unique_columns(room_character_assignments) >= {
        ("session_id", "character_id"),
    }
    assert _unique_columns(room_required_members) >= {
        ("session_id", "member_id"),
        ("session_id", "character_id"),
    }
    assert _unique_columns(room_principal_reservations) >= {
        ("session_id", "member_id"),
    }

    expected_member_foreign_key = (
        ("member_id", "session_id"),
        ("room_members.id", "room_members.session_id"),
        "CASCADE",
    )
    assert expected_member_foreign_key in _foreign_keys(room_character_assignments)
    assert expected_member_foreign_key in _foreign_keys(room_required_members)
    assert (
        ("member_id", "session_id", "principal_id"),
        (
            "room_members.id",
            "room_members.session_id",
            "room_members.principal_id",
        ),
        "CASCADE",
    ) in _foreign_keys(room_principal_reservations)
    assert (
        ("created_by_member_id", "session_id"),
        ("room_members.id", "room_members.session_id"),
        "CASCADE",
    ) in _foreign_keys(room_invites)

    assert room_invites.c.token_hash.type.python_type is bytes
    assert room_invites.c.max_uses.server_default is not None
    assert room_invites.c.uses_count.server_default is not None

    sql = _normalized_sql()
    assert "unique (id, session_id, principal_id)" in sql
    assert (
        "foreign key (member_id, session_id, principal_id) "
        "references public.room_members(id, session_id, principal_id)"
    ) in sql


def test_room_tables_are_service_role_only_and_documented() -> None:
    sql = _normalized_sql()

    for table_name in ROOM_TABLE_NAMES:
        assert f"alter table public.{table_name} enable row level security" in sql
        assert (
            f'create policy "service_role_full_access" on public.{table_name} '
            "for all to service_role using (true) with check (true)"
        ) in sql
        assert f"comment on table public.{table_name} is" in sql
        assert f'comment on policy "service_role_full_access" on public.{table_name} is' in sql

    revoke_match = re.search(
        r"revoke all privileges on table (?P<tables>.+?) from anon, authenticated",
        sql,
    )
    grant_match = re.search(
        r"grant all privileges on table (?P<tables>.+?) to service_role",
        sql,
    )
    assert revoke_match is not None
    assert grant_match is not None
    assert set(re.findall(r"public\.([a-z_]+)", revoke_match.group("tables"))) == ROOM_TABLE_NAMES
    assert set(re.findall(r"public\.([a-z_]+)", grant_match.group("tables"))) == ROOM_TABLE_NAMES


def test_room_constraints_cover_hash_limits_ready_and_required_member_order() -> None:
    checks_by_table = {
        table.name: {
            constraint.name: str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, CheckConstraint)
        }
        for table in (
            room_members,
            room_character_assignments,
            room_invites,
            room_required_members,
        )
    }

    assert "membership_status" in checks_by_table["room_members"]["room_members_ready_check"]
    assert (
        "octet_length(token_hash) = 32"
        == checks_by_table["room_invites"]["room_invites_token_hash_check"]
    )
    assert (
        "uses_count <= max_uses" in checks_by_table["room_invites"]["room_invites_uses_count_check"]
    )
    assert checks_by_table["room_required_members"]["room_required_members_ordinal_check"] == (
        "ordinal >= 0"
    )


def test_scene_presence_is_latest_value_metadata_on_existing_member_table() -> None:
    sql = " ".join(
        re.sub(
            r"--[^\n]*",
            "",
            FORWARD_PRESENCE_MIGRATION.read_text(encoding="utf-8"),
        )
        .lower()
        .split()
    )

    for column in ("scene_x", "scene_y", "scene_facing", "scene_moving", "scene_updated_at"):
        assert column in room_members.c
        assert f"add column {column}" in sql
    assert "room_members_scene_presence_check" in sql
    assert "scene_x between 17 and 2383" in sql
    assert "scene_y between 17 and 1583" in sql
    assert "scene_facing in ('left', 'right')" in sql
    assert "comment on column public.room_members.scene_x" in sql
    assert "never gameplay authority" in sql


def _normalized_sql() -> str:
    without_comments = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    return " ".join(without_comments.lower().split())


def _unique_columns(table: object) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, UniqueConstraint)
    }


def _foreign_keys(table: object) -> set[tuple[tuple[str, ...], tuple[str, ...], str | None]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            tuple(element.target_fullname for element in constraint.elements),
            constraint.ondelete,
        )
        for constraint in table.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, ForeignKeyConstraint)
    }
