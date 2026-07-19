from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from sqlalchemy import CheckConstraint, Index, delete, insert, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from engine.core.checkpoint import CheckpointAttemptFencedError, SupabaseSessionCheckpointSaver
from engine.core.checkpoint_models import checkpoint_config
from engine.db.session import build_async_database_url, build_connect_args
from engine.db.tables import (
    game_sessions,
    script_packages,
    session_checkpoints,
    session_command_receipts,
    session_events,
)
from engine.repositories.session_command_repository import SessionCommandRepository

DATABASE_URL_ENV = "AISCRIPTKILL_MP3_RECOVERY_DB_URL"
MIGRATION_ROOT = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
BASE_STATE: dict[str, object] = {
    "session_id": "private-recovery-state",
    "answer_key": {"culprit": "private"},
}
BASE_STATE_SHA256 = "a" * 64
REQUEST_SHA256 = "b" * 64


def test_stale_recovery_schema_pairs_private_base_state_and_processing_lease() -> None:
    sql = " ".join(
        path.read_text(encoding="utf-8")
        for path in sorted(MIGRATION_ROOT.glob("*.sql"))
    ).lower()
    normalized = " ".join(sql.split())

    assert "add column base_state jsonb" in normalized
    assert "add column base_state_sha256 text" in normalized
    assert "jsonb_typeof(base_state) = 'object'" in normalized
    assert "base_state is null and base_state_sha256 is null" in normalized
    assert "base_state is not null" in normalized
    assert "base_state_sha256 is not null" in normalized
    assert "base_state_sha256 ~ '^[0-9a-f]{64}$'" in normalized
    assert "session_command_receipts_processing_lease_check" in normalized
    assert (
        "revoke all privileges on table public.session_command_receipts, public.session_events "
        "from anon, authenticated"
    ) in normalized
    assert (
        'create policy "service_role_full_access" on public.session_command_receipts '
        "for all to service_role using (true) with check (true)"
    ) in normalized

    assert isinstance(session_command_receipts.c.base_state.type, JSONB)
    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in session_command_receipts.constraints
        if isinstance(constraint, CheckConstraint)
    }
    pair_check = checks["session_command_receipts_base_state_check"]
    assert "base_state IS NULL AND base_state_sha256 IS NULL" in pair_check
    assert "base_state IS NOT NULL" in pair_check
    assert "base_state_sha256 IS NOT NULL" in pair_check
    assert "^[0-9a-f]{64}$" in checks["session_command_receipts_base_state_hash_check"]
    lease_check = checks["session_command_receipts_processing_lease_check"]
    assert "status = 'processing'" in lease_check
    assert "lease_expires_at IS NOT NULL" in lease_check

    processing_indexes = [
        index
        for index in session_command_receipts.indexes
        if _processing_index(index)
    ]
    assert any(index.unique for index in processing_indexes)
    assert any(
        tuple(column.name for column in index.columns) == ("session_id",)
        for index in processing_indexes
        if index.unique
    )


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_postgres_reclaims_one_expired_attempt_and_fences_stale_finalization() -> None:
    engine = _database_engine(_required_database_url())
    script_id = f"mp3-stale-reclaim-{uuid4().hex}"
    session_id = uuid4()
    first_command_id = uuid4()
    second_command_id = uuid4()
    await _seed_session(engine, script_id, session_id)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            repository = SessionCommandRepository(db)
            claimed = await repository.claim_receipt(
                session_id=session_id,
                command_id=first_command_id,
                request_payload={"action": "open_clue_board", "expected_revision": 0},
                request_sha256=REQUEST_SHA256,
                expected_revision=0,
                base_revision=0,
                base_state=BASE_STATE,
                base_state_sha256=BASE_STATE_SHA256,
            )
            assert claimed is not None
            await db.commit()

            competing = await repository.claim_receipt(
                session_id=session_id,
                command_id=second_command_id,
                request_payload={"action": "open_clue_board", "expected_revision": 0},
                request_sha256="c" * 64,
                expected_revision=0,
                base_revision=0,
                base_state=BASE_STATE,
                base_state_sha256=BASE_STATE_SHA256,
            )
            assert competing is None
            await db.rollback()

            await db.execute(
                update(session_command_receipts)
                .where(
                    session_command_receipts.c.session_id == session_id,
                    session_command_receipts.c.command_id == first_command_id,
                )
                .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )
            await db.commit()

        reclaimed = await asyncio.gather(
            _reclaim_once(factory, session_id, first_command_id),
            _reclaim_once(factory, session_id, first_command_id),
        )
        winners = [receipt for receipt in reclaimed if receipt is not None]
        assert len(winners) == 1
        assert winners[0].attempt_count == 2
        assert winners[0].base_state == BASE_STATE
        assert winners[0].base_state_sha256 == BASE_STATE_SHA256

        async with factory() as db:
            repository = SessionCommandRepository(db)
            stale_finalized = await repository.finalize_success(
                session_id=session_id,
                command_id=first_command_id,
                attempt_count=1,
                result=_success_result(),
                revision=1,
                event_sequence=1,
                event_payload={"result": _success_result()},
            )
            assert stale_finalized is False
            await db.commit()

            receipt = await repository.get_receipt(session_id, first_command_id)
            assert receipt is not None
            assert receipt.status == "processing"
            assert receipt.attempt_count == 2
            events = (
                await db.execute(
                    select(session_events.c.sequence).where(
                        session_events.c.session_id == session_id
                    )
                )
            ).all()
            assert events == []
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_postgres_reclaimed_attempt_fences_old_checkpoint_writer() -> None:
    engine = _database_engine(_required_database_url())
    script_id = f"mp3-checkpoint-fence-{uuid4().hex}"
    session_id = uuid4()
    command_id = uuid4()
    await _seed_session(engine, script_id, session_id)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as db:
            repository = SessionCommandRepository(db)
            claimed = await repository.claim_receipt(
                session_id=session_id,
                command_id=command_id,
                request_payload={"action": "open_clue_board", "expected_revision": 0},
                request_sha256=REQUEST_SHA256,
                expected_revision=0,
                base_revision=0,
                base_state=BASE_STATE,
                base_state_sha256=BASE_STATE_SHA256,
            )
            assert claimed is not None
            await db.execute(
                update(session_command_receipts)
                .where(
                    session_command_receipts.c.session_id == session_id,
                    session_command_receipts.c.command_id == command_id,
                )
                .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )
            await db.commit()

        async with factory() as reclaim_db:
            reclaimed = await SessionCommandRepository(reclaim_db).reclaim_expired_receipt(
                session_id,
                command_id,
                1,
            )
            assert reclaimed is not None
            assert reclaimed.attempt_count == 2
            await reclaim_db.commit()

        checkpoint = empty_checkpoint()
        checkpoint["id"] = "00000000-0000-6000-8000-000000000001"
        async with factory() as stale_db:
            stale_saver = SupabaseSessionCheckpointSaver(stale_db)
            with pytest.raises(CheckpointAttemptFencedError):
                await stale_saver.aput(
                    checkpoint_config(
                        str(session_id),
                        command_id=str(command_id),
                        command_attempt=1,
                    ),
                    checkpoint,
                    {"source": "input"},
                    {},
                )

        async with factory() as winner_db:
            winner_saver = SupabaseSessionCheckpointSaver(winner_db)
            await winner_saver.aput(
                checkpoint_config(
                    str(session_id),
                    command_id=str(command_id),
                    command_attempt=2,
                ),
                checkpoint,
                {"source": "input"},
                {},
            )

        async with factory() as verify_db:
            rows = (
                await verify_db.execute(
                    select(
                        session_checkpoints.c.command_id,
                        session_checkpoints.c.command_attempt,
                    ).where(session_checkpoints.c.session_id == session_id)
                )
            ).all()
            assert rows == [(command_id, 2)]
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


def _processing_index(index: Index) -> bool:
    predicate = index.dialect_options["postgresql"].get("where")
    return predicate is not None and "processing" in str(predicate)


async def _reclaim_once(
    factory: async_sessionmaker[AsyncSession],
    session_id: UUID,
    command_id: UUID,
):
    async with factory() as db:
        receipt = await SessionCommandRepository(db).reclaim_expired_receipt(
            session_id,
            command_id,
            1,
        )
        await db.commit()
        return receipt


def _success_result() -> dict[str, object]:
    return {
        "type": "npc_response",
        "character_id": "guide",
        "text": "继续调查。",
        "emotion": "calm",
        "state_changes": {},
        "triggered_events": [],
        "media_triggers": [],
    }


def _database_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(
        build_async_database_url(database_url),
        connect_args=build_connect_args(database_url),
    )


def _required_database_url() -> str:
    value = os.getenv(DATABASE_URL_ENV)
    if value is None or value == "":
        raise RuntimeError(f"missing {DATABASE_URL_ENV}")
    return value


async def _seed_session(engine: AsyncEngine, script_id: str, session_id: UUID) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            insert(script_packages).values(
                id=script_id,
                name="MP-3 stale recovery fencing",
                version="1.0.0",
                config={},
                status="published",
            )
        )
        await connection.execute(
            insert(game_sessions).values(
                id=session_id,
                script_id=script_id,
                player_id=None,
                player_character_id="player",
                state={},
                status="in_progress",
            )
        )


async def _remove_script(engine: AsyncEngine, script_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            delete(game_sessions).where(game_sessions.c.script_id == script_id)
        )
        await connection.execute(delete(script_packages).where(script_packages.c.id == script_id))
