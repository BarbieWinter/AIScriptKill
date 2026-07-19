import re
from pathlib import Path

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from engine.db.session import REQUIRED_PUBLIC_TABLES
from engine.db.tables import metadata, session_command_receipts, session_events

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "supabase"
    / "migrations"
    / "20260718010000_mp3_command_receipts_events.sql"
)
MP3_TABLE_NAMES = {"session_command_receipts", "session_events"}


def test_mp3_tables_are_required_and_present_in_metadata() -> None:
    assert MP3_TABLE_NAMES <= set(REQUIRED_PUBLIC_TABLES)
    assert MP3_TABLE_NAMES <= set(metadata.tables)


def test_command_receipt_identity_status_and_actor_constraints() -> None:
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


def test_mp3_migration_has_checkpoint_marker_and_service_role_only_boundary() -> None:
    sql = _normalized_sql()

    assert "alter table public.session_checkpoints add column command_id uuid" in sql
    assert "create index idx_session_checkpoints_session_command" in sql
    assert "where command_id is not null" in sql

    for table_name in MP3_TABLE_NAMES:
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
    assert set(re.findall(r"public\.([a-z_]+)", revoke_match.group("tables"))) == MP3_TABLE_NAMES
    assert set(re.findall(r"public\.([a-z_]+)", grant_match.group("tables"))) == MP3_TABLE_NAMES


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
