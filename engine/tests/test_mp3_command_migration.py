import re
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from engine.db.session import REQUIRED_PUBLIC_TABLES
from engine.db.tables import (
    metadata,
    room_outbox,
    session_command_identities,
    session_command_receipts,
    session_events,
)

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260718010000_mp3_command_receipts_events.sql"
)
GLOBAL_IDENTITY_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260720010000_mp3_global_command_identity.sql"
)
IDENTITY_COMMENT_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260720030000_mp3_command_identity_comment.sql"
)
IDENTITY_TOMBSTONE_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260720040000_mp3_command_identity_tombstones.sql"
)
OUTBOX_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260720020000_mp3_room_outbox.sql"
)
OUTBOX_INTEGRITY_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260720050000_mp3_outbox_session_event_integrity.sql"
)
OUTBOX_RELAY_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260730010000_room_event_relay_leases.sql"
)
MP3_BASE_TABLE_NAMES = {"session_command_receipts", "session_events"}
MP3_TABLE_NAMES = {
    *MP3_BASE_TABLE_NAMES,
    "room_outbox",
    "session_command_identities",
}


def test_mp3_tables_are_required_and_present_in_metadata() -> None:
    assert MP3_TABLE_NAMES <= set(REQUIRED_PUBLIC_TABLES)
    assert MP3_TABLE_NAMES <= set(metadata.tables)


def test_command_receipt_identity_status_and_actor_constraints() -> None:
    assert ("command_id",) in _unique_columns(session_command_receipts)
    assert ("session_id", "command_id") in _unique_columns(session_command_receipts)

    checks = _checks(session_command_receipts)
    assert "processing" in str(checks["session_command_receipts_status_check"])
    assert "succeeded" in str(checks["session_command_receipts_status_payload_check"])
    assert "completed_at" in str(checks["session_command_receipts_completed_check"])
    assert "actor_principal_id IS NOT NULL" in str(checks["session_command_receipts_actor_check"])
    assert "state_sha256" in str(checks["session_command_receipts_state_hash_check"])

    assert (
        ("actor_member_id", "session_id", "actor_principal_id"),
        (
            "room_members.id",
            "room_members.session_id",
            "room_members.principal_id",
        ),
        "RESTRICT",
    ) in _foreign_keys(session_command_receipts)


def test_global_command_identity_is_a_forward_migration() -> None:
    sql = " ".join(GLOBAL_IDENTITY_MIGRATION.read_text(encoding="utf-8").lower().split())

    assert "group by command_id having count(*) > 1" in sql
    assert "add constraint uq_session_command_receipts_command unique (command_id)" in sql
    assert "permanently binds one room, actor, request, and terminal result" in sql
    comment_sql = " ".join(IDENTITY_COMMENT_MIGRATION.read_text(encoding="utf-8").lower().split())
    assert "unique across all live session receipts" in comment_sql
    tombstone_sql = " ".join(
        IDENTITY_TOMBSTONE_MIGRATION.read_text(encoding="utf-8").lower().split()
    )
    assert "create table public.session_command_identities" in tombstone_sql
    assert "before insert on public.session_command_receipts" in tombstone_sql
    assert "after insert on public.session_command_receipts" in tombstone_sql
    assert "on conflict (command_id) do nothing" in tombstone_sql
    assert "permanent deployment-wide command uuid tombstones" in tombstone_sql
    assert session_command_identities.c.command_id.primary_key


def test_session_events_have_ordering_command_and_positive_cursor_constraints() -> None:
    assert _unique_columns(session_events) >= {
        ("session_id", "sequence"),
        ("session_id", "command_id"),
    }
    assert (
        ("session_id", "command_id"),
        (
            "session_command_receipts.session_id",
            "session_command_receipts.command_id",
        ),
        "CASCADE",
    ) in _foreign_keys(session_events)

    checks = _checks(session_events)
    assert str(checks["session_events_sequence_check"]) == "sequence > 0"
    assert str(checks["session_events_revision_check"]) == "revision >= 0"


def test_room_outbox_has_event_topic_deduplication_and_retry_state() -> None:
    assert ("room_event_id", "topic") in _unique_columns(room_outbox)
    assert {
        "attempts",
        "available_at",
        "published_at",
        "last_error",
        "lease_token",
        "lease_owner",
        "lease_expires_at",
        "poisoned_at",
        "poison_reason",
    } <= {column.name for column in room_outbox.columns}
    checks = _checks(room_outbox)
    assert "attempts >= 0" in str(checks["room_outbox_attempts_check"])
    assert "lease_token IS NULL" in str(checks["room_outbox_lease_check"])
    assert "poisoned_at IS NULL" in str(checks["room_outbox_poison_check"])
    assert "published_at IS NULL" in str(checks["room_outbox_terminal_state_check"])

    sql = " ".join(OUTBOX_MIGRATION.read_text(encoding="utf-8").lower().split())
    assert "create table public.room_outbox" in sql
    assert "unique (room_event_id, topic)" in sql
    integrity_sql = " ".join(OUTBOX_INTEGRITY_MIGRATION.read_text(encoding="utf-8").lower().split())
    assert "foreign key (session_id, room_event_id)" in integrity_sql
    assert "references public.session_events(session_id, id)" in integrity_sql
    relay_sql = " ".join(OUTBOX_RELAY_MIGRATION.read_text(encoding="utf-8").lower().split())
    assert "add column lease_token uuid" in relay_sql
    assert "add column lease_owner text" in relay_sql
    assert "add column lease_expires_at timestamptz" in relay_sql
    assert "add column poisoned_at timestamptz" in relay_sql
    assert "add column poison_reason text" in relay_sql
    assert "where published_at is null and poisoned_at is null" in relay_sql
    assert "lease_expires_at" in relay_sql
    assert "revoke all privileges on table public.room_outbox from anon, authenticated" in relay_sql
    assert "grant all privileges on table public.room_outbox to service_role" in relay_sql


def test_mp3_migration_has_checkpoint_marker_and_service_role_only_boundary() -> None:
    sql = _normalized_sql()

    assert "alter table public.session_checkpoints add column command_id uuid" in sql
    assert "create index idx_session_checkpoints_session_command" in sql
    assert "where command_id is not null" in sql

    for table_name in MP3_BASE_TABLE_NAMES:
        assert f"alter table public.{table_name} enable row level security" in sql
        assert (
            f'create policy "service_role_full_access" on public.{table_name} '
            "for all to service_role using (true) with check (true)"
        ) in sql

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
    assert (
        set(re.findall(r"public\.([a-z_]+)", revoke_match.group("tables"))) == MP3_BASE_TABLE_NAMES
    )
    assert (
        set(re.findall(r"public\.([a-z_]+)", grant_match.group("tables"))) == MP3_BASE_TABLE_NAMES
    )


def _normalized_sql() -> str:
    without_comments = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))
    return " ".join(without_comments.lower().split())


def _checks(table: object) -> dict[str, object]:
    return {
        constraint.name: constraint.sqltext
        for constraint in table.constraints  # type: ignore[attr-defined]
        if isinstance(constraint, CheckConstraint)
    }


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
