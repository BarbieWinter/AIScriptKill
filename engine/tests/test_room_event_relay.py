from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import asyncpg
import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

import engine.relay.main as relay_main
from engine.api.config import Settings
from engine.db.session import build_async_database_url, build_connect_args
from engine.db.tables import (
    game_sessions,
    room_outbox,
    script_packages,
    session_command_receipts,
    session_events,
)
from engine.relay.main import create_room_event_relay_app
from engine.services.room_event_relay import RoomEventRelay, RoomEventRelayConfig
from engine.services.room_event_transport import PostgresNotifyRoomOutboxPublisher
from engine.services.room_outbox import (
    RoomOutboxBatchResult,
    RoomOutboxMessage,
    acknowledge_room_outbox_failure,
    acknowledge_room_outbox_success,
    claim_room_outbox_batch,
    publish_room_outbox_batch,
    read_room_outbox_health,
)

DATABASE_URL_ENV = "AISCRIPTKILL_ROOM_EVENT_RELAY_DB_URL"


@dataclass(frozen=True, slots=True)
class SeededOutbox:
    script_id: str
    session_id: UUID
    event_ids: tuple[UUID, ...]
    outbox_ids: tuple[UUID, ...]


def test_relay_config_requires_lease_to_outlive_publish_timeout() -> None:
    with pytest.raises(ValueError, match="lease_seconds must exceed"):
        RoomEventRelayConfig(
            batch_size=1,
            poll_seconds=0.1,
            lease_seconds=5,
            publish_timeout_seconds=5,
            retry_base_seconds=1,
            retry_max_seconds=2,
            max_attempts=2,
        )


async def test_relay_stops_when_a_cycle_cannot_access_relay_infrastructure() -> None:
    class FatalCycleRelay(RoomEventRelay):
        async def run_once(self) -> RoomOutboxBatchResult:
            raise RuntimeError("database unavailable")

    relay = FatalCycleRelay(
        cast(Any, None),
        cast(Any, None),
        worker_id="relay-fatal-cycle-test",
        config=RoomEventRelayConfig(
            batch_size=1,
            poll_seconds=60,
            lease_seconds=5,
            publish_timeout_seconds=1,
            retry_base_seconds=1,
            retry_max_seconds=2,
            max_attempts=3,
        ),
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await relay.run(asyncio.Event())

    assert relay.status.running is False
    assert relay.status.ready is False
    assert relay.status.last_cycle_error == "RuntimeError"


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_relay_claim_releases_database_lock_before_transport_publish() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)

    class LockProbePublisher:
        def __init__(self) -> None:
            self.messages: list[RoomOutboxMessage] = []

        async def publish(self, message: RoomOutboxMessage) -> None:
            async with factory() as probe:
                await probe.execute(
                    select(room_outbox.c.id)
                    .where(room_outbox.c.id == seeded.outbox_ids[0])
                    .with_for_update(nowait=True)
                )
                await probe.rollback()
            self.messages.append(message)

    publisher = LockProbePublisher()
    try:
        result = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="relay-lock-probe",
            limit=1,
        )

        assert result == RoomOutboxBatchResult(
            claimed=1,
            published=1,
            failed=0,
            poisoned=0,
            stale=0,
        )
        assert [message.event_id for message in publisher.messages] == list(seeded.event_ids)

        async with factory() as db:
            row = (
                (
                    await db.execute(
                        select(room_outbox).where(room_outbox.c.id == seeded.outbox_ids[0])
                    )
                )
                .mappings()
                .one()
            )
        assert row["attempts"] == 1
        assert row["failure_attempts"] == 0
        assert row["published_at"] is not None
        assert row["lease_token"] is None
        assert row["lease_owner"] is None
        assert row["lease_expires_at"] is None
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_concurrent_workers_cannot_share_one_active_lease() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)

    async def claim(worker_id: str):
        async with factory() as db:
            leases = await claim_room_outbox_batch(
                db,
                worker_id=worker_id,
                limit=1,
                lease_seconds=30,
            )
            await db.commit()
            return leases

    try:
        first_claims, second_claims = await asyncio.gather(
            claim("relay-concurrent-a"),
            claim("relay-concurrent-b"),
        )

        concurrent_claims = (*first_claims, *second_claims)
        seeded_claims = [
            lease for lease in concurrent_claims if lease.outbox_id == seeded.outbox_ids[0]
        ]
        assert len(seeded_claims) == 1

        third_claims = await claim("relay-concurrent-c")
        assert all(lease.outbox_id != seeded.outbox_ids[0] for lease in third_claims)
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_relay_batch_publishes_concurrently_within_lease_window() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=3)

    class BarrierPublisher:
        def __init__(self) -> None:
            self.started = 0
            self.all_started = asyncio.Event()

        async def publish(self, _message: RoomOutboxMessage) -> None:
            self.started += 1
            if self.started == 3:
                self.all_started.set()
            await self.all_started.wait()

    publisher = BarrierPublisher()
    try:
        result = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="relay-batch-concurrency",
            limit=3,
            lease_seconds=5,
            publish_timeout_seconds=1,
        )

        assert publisher.started == 3
        assert result == RoomOutboxBatchResult(
            claimed=3,
            published=3,
            failed=0,
            poisoned=0,
            stale=0,
        )
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_expired_lease_recovery_duplicates_stable_identity_and_fences_stale_ack() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)
    delivered: list[RoomOutboxMessage] = []
    try:
        async with factory() as first_db:
            first_claims = await claim_room_outbox_batch(
                first_db,
                worker_id="relay-before-restart",
                limit=1,
                lease_seconds=30,
            )
            await first_db.commit()
        assert len(first_claims) == 1
        delivered.append(first_claims[0].message)

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.id == seeded.outbox_ids[0])
                .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )

        async with factory() as second_db:
            second_claims = await claim_room_outbox_batch(
                second_db,
                worker_id="relay-after-restart",
                limit=1,
                lease_seconds=30,
            )
            await second_db.commit()
        assert len(second_claims) == 1
        delivered.append(second_claims[0].message)

        assert delivered == [first_claims[0].message, first_claims[0].message]
        assert first_claims[0].lease_token != second_claims[0].lease_token
        assert first_claims[0].attempts == 1
        assert second_claims[0].attempts == 2
        assert first_claims[0].failure_attempts == 0
        assert second_claims[0].failure_attempts == 0

        async with factory() as stale_db:
            stale_acknowledged = await acknowledge_room_outbox_success(
                stale_db,
                first_claims[0],
            )
            await stale_db.commit()
        assert stale_acknowledged is False

        async with factory() as winner_db:
            winner_acknowledged = await acknowledge_room_outbox_success(
                winner_db,
                second_claims[0],
            )
            await winner_db.commit()
        assert winner_acknowledged is True

        async with factory() as verify_db:
            row = (
                (
                    await verify_db.execute(
                        select(room_outbox).where(room_outbox.c.id == seeded.outbox_ids[0])
                    )
                )
                .mappings()
                .one()
            )
        assert row["attempts"] == 2
        assert row["failure_attempts"] == 0
        assert row["published_at"] is not None
        assert row["lease_token"] is None
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_expired_claim_recovery_does_not_consume_failure_budget() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)
    try:
        for recovery in range(4):
            async with factory() as claim_db:
                leases = await claim_room_outbox_batch(
                    claim_db,
                    worker_id=f"relay-crashed-{recovery}",
                    limit=1,
                    lease_seconds=30,
                )
                await claim_db.commit()
            assert len(leases) == 1
            assert leases[0].failure_attempts == 0
            async with engine.begin() as connection:
                await connection.execute(
                    update(room_outbox)
                    .where(room_outbox.c.id == seeded.outbox_ids[0])
                    .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
                )

        async with factory() as failure_db:
            outcome = await acknowledge_room_outbox_failure(
                failure_db,
                leases[0],
                error_name="RuntimeError",
                retry_base_seconds=1,
                retry_max_seconds=4,
                max_attempts=2,
            )
            await failure_db.commit()

        assert outcome == "retry"
        async with factory() as verify_db:
            row = (
                (
                    await verify_db.execute(
                        select(room_outbox).where(room_outbox.c.id == seeded.outbox_ids[0])
                    )
                )
                .mappings()
                .one()
            )
        assert row["attempts"] == 4
        assert row["failure_attempts"] == 1
        assert row["poisoned_at"] is None
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_failure_ack_uses_lease_token_after_expiry_until_reclaimed() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)
    try:
        async with factory() as claim_db:
            leases = await claim_room_outbox_batch(
                claim_db,
                worker_id="relay-delayed-ack",
                limit=1,
                lease_seconds=30,
            )
            await claim_db.commit()
        assert len(leases) == 1

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.id == seeded.outbox_ids[0])
                .values(lease_expires_at=datetime(2000, 1, 1, tzinfo=UTC))
            )

        async with factory() as failure_db:
            outcome = await acknowledge_room_outbox_failure(
                failure_db,
                leases[0],
                error_name="TimeoutError",
                retry_base_seconds=1,
                retry_max_seconds=4,
                max_attempts=2,
            )
            await failure_db.commit()

        assert outcome == "retry"
        async with factory() as verify_db:
            row = (
                (
                    await verify_db.execute(
                        select(room_outbox).where(room_outbox.c.id == seeded.outbox_ids[0])
                    )
                )
                .mappings()
                .one()
            )
        assert row["failure_attempts"] == 1
        assert row["last_error"] == "TimeoutError"
        assert row["lease_token"] is None
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_failure_backoff_and_poison_do_not_block_later_healthy_event() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as baseline_db:
        baseline_health = await read_room_outbox_health(baseline_db)
    seeded = await _seed_outbox_events(engine, count=2)

    class SelectivePublisher:
        def __init__(self) -> None:
            self.messages: list[RoomOutboxMessage] = []

        async def publish(self, message: RoomOutboxMessage) -> None:
            self.messages.append(message)
            if message.event_id == seeded.event_ids[0]:
                raise RuntimeError("must not be persisted or exposed")

    publisher = SelectivePublisher()
    try:
        first = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="relay-poison-test",
            limit=2,
            retry_base_seconds=1,
            retry_max_seconds=4,
            max_attempts=2,
        )
        assert first == RoomOutboxBatchResult(
            claimed=2,
            published=1,
            failed=1,
            poisoned=0,
            stale=0,
        )

        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        select(room_outbox)
                        .where(room_outbox.c.session_id == seeded.session_id)
                        .order_by(room_outbox.c.room_event_id)
                    )
                )
                .mappings()
                .all()
            )
        by_event = {row["room_event_id"]: row for row in rows}
        failed_row = by_event[seeded.event_ids[0]]
        healthy_row = by_event[seeded.event_ids[1]]
        assert failed_row["attempts"] == 1
        assert failed_row["failure_attempts"] == 1
        assert failed_row["published_at"] is None
        assert failed_row["available_at"] > datetime.now(UTC)
        assert failed_row["last_error"] == "RuntimeError"
        assert "must not be persisted" not in failed_row["last_error"]
        assert failed_row["poisoned_at"] is None
        assert healthy_row["published_at"] is not None

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.room_event_id == seeded.event_ids[0])
                .values(available_at=datetime(1970, 1, 1, tzinfo=UTC))
            )

        second = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="relay-poison-test",
            limit=1,
            retry_base_seconds=1,
            retry_max_seconds=4,
            max_attempts=2,
        )
        assert second == RoomOutboxBatchResult(
            claimed=1,
            published=0,
            failed=1,
            poisoned=1,
            stale=0,
        )

        async with factory() as db:
            poisoned = (
                (
                    await db.execute(
                        select(room_outbox).where(
                            room_outbox.c.room_event_id == seeded.event_ids[0]
                        )
                    )
                )
                .mappings()
                .one()
            )
            health = await read_room_outbox_health(db)
        assert poisoned["attempts"] == 2
        assert poisoned["failure_attempts"] == 2
        assert poisoned["poisoned_at"] is not None
        assert poisoned["poison_reason"] == "RuntimeError"
        assert poisoned["lease_token"] is None
        assert health.pending_count == baseline_health.pending_count
        assert health.active_leases == baseline_health.active_leases
        assert health.expired_leases == baseline_health.expired_leases
        assert health.poisoned_count == baseline_health.poisoned_count + 1
        assert health.retry_attempts == baseline_health.retry_attempts + 2
        assert health.last_published_at is not None
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_postgres_notify_adapter_publishes_only_bounded_event_reference() -> None:
    database_url = _required_database_url()
    engine = _database_engine(database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    channel = f"aiscriptkill_test_{uuid4().hex}"
    received: list[str] = []
    notification = asyncio.Event()
    listener = await asyncpg.connect(_asyncpg_database_url(database_url), statement_cache_size=0)

    def receive_notification(
        _connection: asyncpg.Connection,
        _pid: int,
        _channel: str,
        payload: str,
    ) -> None:
        received.append(payload)
        notification.set()

    await listener.add_listener(channel, receive_notification)
    publisher = PostgresNotifyRoomOutboxPublisher(factory, channel=channel)
    message = RoomOutboxMessage(
        event_id=uuid4(),
        session_id=uuid4(),
        topic="room.events.v1",
        sequence=7,
        revision=4,
        event_type="gameplay.command_succeeded",
        event_version=1,
        payload={
            "command_type": "settlement.submit",
            "private_state": {"secret": "must-not-cross-transport"},
        },
    )
    try:
        await publisher.publish(message)
        await asyncio.wait_for(notification.wait(), timeout=2)

        assert len(received) == 1
        payload = json.loads(received[0])
        assert payload == {
            "protocol_version": 1,
            "topic": "room.events.v1",
            "session_id": str(message.session_id),
            "event_id": str(message.event_id),
            "sequence": 7,
        }
        assert "private_state" not in received[0]
        assert "must-not-cross-transport" not in received[0]
        assert len(received[0].encode("utf-8")) < 512
    finally:
        await listener.remove_listener(channel, receive_notification)
        await listener.close()
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_relay_runtime_times_out_publish_and_shuts_down_within_bound() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)
    publish_started = asyncio.Event()

    class HangingPublisher:
        async def publish(self, _message: RoomOutboxMessage) -> None:
            publish_started.set()
            await asyncio.Event().wait()

    relay = RoomEventRelay(
        factory,
        HangingPublisher(),
        worker_id="relay-shutdown-test",
        config=RoomEventRelayConfig(
            batch_size=1,
            poll_seconds=60,
            lease_seconds=5,
            publish_timeout_seconds=0.05,
            retry_base_seconds=1,
            retry_max_seconds=2,
            max_attempts=5,
        ),
    )
    stop = asyncio.Event()
    task = asyncio.create_task(relay.run(stop))
    try:
        await asyncio.wait_for(publish_started.wait(), timeout=1)
        stop.set()
        await asyncio.wait_for(task, timeout=1)

        assert relay.status.running is False
        assert relay.status.ready is False
        assert relay.status.last_cycle_at is not None
        assert relay.status.last_cycle_error == "PublicationFailed"
        assert relay.status.last_batch is not None
        assert relay.status.last_batch.failed == 1

        async with factory() as db:
            row = (
                (
                    await db.execute(
                        select(room_outbox).where(room_outbox.c.id == seeded.outbox_ids[0])
                    )
                )
                .mappings()
                .one()
            )
        assert row["last_error"] == "TimeoutError"
        assert row["lease_token"] is None
    finally:
        stop.set()
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_relay_process_exposes_ready_and_aggregate_lag_without_identifiers() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)
    published = asyncio.Event()

    class RecordingPublisher:
        async def publish(self, _message: RoomOutboxMessage) -> None:
            published.set()

    async def no_dispose() -> None:
        return None

    settings = Settings(
        **cast(
            dict[str, Any],
            {
                "_env_file": None,
                "ROOM_EVENTS_V1": True,
                "ROOM_EVENT_RELAY_BATCH_SIZE": 1,
                "ROOM_EVENT_RELAY_POLL_SECONDS": 60,
                "ROOM_EVENT_RELAY_LEASE_SECONDS": 5,
                "ROOM_EVENT_RELAY_PUBLISH_TIMEOUT_SECONDS": 1,
                "ROOM_EVENT_RELAY_SHUTDOWN_GRACE_SECONDS": 1,
            },
        )
    )
    app = create_room_event_relay_app(
        settings=settings,
        factory=factory,
        publisher=RecordingPublisher(),
        dispose=no_dispose,
        worker_id="relay-health-test",
    )
    try:
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(published.wait(), timeout=1)
            await _wait_for_relay_ready(app)
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://relay",
            ) as client:
                live_response = await client.get("/health")
                ready_response = await client.get("/health/ready")

            assert live_response.status_code == 200
            assert live_response.json() == {
                "status": "ok",
                "service": "room-event-relay",
                "version": 1,
            }
            assert ready_response.status_code == 200
            payload = ready_response.json()
            assert payload["status"] == "ready"
            assert payload["running"] is True
            assert payload["pending_count"] >= 0
            assert payload["active_leases"] >= 0
            assert payload["expired_leases"] >= 0
            assert payload["poisoned_count"] >= 0
            assert payload["retry_attempts"] >= 0
            assert payload["last_cycle_at"] is not None
            assert payload["last_published_at"] is not None
            assert "last_error" not in payload
            assert str(seeded.session_id) not in ready_response.text
            assert str(seeded.event_ids[0]) not in ready_response.text
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_relay_readiness_stays_failed_until_transport_recovers() -> None:
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    seeded = await _seed_outbox_events(engine, count=1)

    class RecoveringPublisher:
        def __init__(self) -> None:
            self.available = False

        async def publish(self, _message: RoomOutboxMessage) -> None:
            if not self.available:
                raise RuntimeError("transport unavailable")

    publisher = RecoveringPublisher()
    relay = RoomEventRelay(
        factory,
        publisher,
        worker_id="relay-readiness-test",
        config=RoomEventRelayConfig(
            batch_size=1,
            poll_seconds=60,
            lease_seconds=5,
            publish_timeout_seconds=1,
            retry_base_seconds=1,
            retry_max_seconds=2,
            max_attempts=3,
        ),
    )
    try:
        failed = await relay.run_once()
        relay.record_cycle(failed)
        assert relay.status.ready is False

        no_success = await relay.run_once()
        relay.record_cycle(no_success)
        assert no_success.published == 0
        assert relay.status.ready is False

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.id == seeded.outbox_ids[0])
                .values(available_at=datetime(1970, 1, 1, tzinfo=UTC))
            )
        publisher.available = True
        recovered = await relay.run_once()
        relay.record_cycle(recovered)
        assert recovered.published == 1
        assert relay.status.ready is True
    finally:
        await _remove_script(engine, seeded.script_id)
        await engine.dispose()


async def test_relay_process_requests_termination_when_background_relay_crashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CrashingRelay:
        def __init__(self) -> None:
            self.status = type("Status", (), {"running": False})()

        async def run(self, _stop: asyncio.Event) -> None:
            raise RuntimeError("relay crashed")

        async def health(self):
            raise AssertionError("health is not used in this test")

    termination_requested = asyncio.Event()

    def stop_process() -> None:
        termination_requested.set()

    settings = Settings(
        **cast(
            dict[str, Any],
            {
                "_env_file": None,
                "ROOM_EVENTS_V1": True,
                "ROOM_EVENT_RELAY_SHUTDOWN_GRACE_SECONDS": 1,
            },
        )
    )
    crashing_relay = CrashingRelay()
    monkeypatch.setattr(relay_main, "RoomEventRelay", lambda *_args, **_kwargs: crashing_relay)

    async def no_dispose() -> None:
        return None

    app = create_room_event_relay_app(
        settings=settings,
        dispose=no_dispose,
        stop_process=stop_process,
    )
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(termination_requested.wait(), timeout=1)

    assert termination_requested.is_set()


async def test_relay_shutdown_allows_a_bounded_publish_to_finish(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    publish_finished = asyncio.Event()

    class PublishingRelay:
        def __init__(self) -> None:
            self.status = type("Status", (), {"running": False})()

        async def run(self, stop: asyncio.Event) -> None:
            await asyncio.sleep(0.4)
            publish_finished.set()
            await stop.wait()

        async def health(self):
            raise AssertionError("health is not used in this test")

    settings = Settings(
        **cast(
            dict[str, Any],
            {
                "_env_file": None,
                "ROOM_EVENTS_V1": True,
                "ROOM_EVENT_RELAY_SHUTDOWN_GRACE_SECONDS": 1,
            },
        )
    )
    monkeypatch.setattr(relay_main, "RoomEventRelay", lambda *_args, **_kwargs: PublishingRelay())

    async def no_dispose() -> None:
        return None

    app = create_room_event_relay_app(settings=settings, dispose=no_dispose)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)

    assert publish_finished.is_set()


async def test_relay_shutdown_reserves_time_to_dispose_after_cancelling_a_slow_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class SlowStoppingRelay:
        def __init__(self) -> None:
            self.status = type("Status", (), {"running": False})()

        async def run(self, _stop: asyncio.Event) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0.3)
                raise

        async def health(self):
            raise AssertionError("health is not used in this test")

    disposed = asyncio.Event()

    async def dispose() -> None:
        await asyncio.sleep(0.4)
        disposed.set()

    settings = Settings(
        **cast(
            dict[str, Any],
            {
                "_env_file": None,
                "ROOM_EVENTS_V1": True,
                "ROOM_EVENT_RELAY_SHUTDOWN_GRACE_SECONDS": 1,
            },
        )
    )
    monkeypatch.setattr(relay_main, "RoomEventRelay", lambda *_args, **_kwargs: SlowStoppingRelay())
    app = create_room_event_relay_app(settings=settings, dispose=dispose)

    async with app.router.lifespan_context(app):
        await asyncio.sleep(0)

    assert disposed.is_set()


def test_supported_stack_runs_relay_independently_from_request_workers() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repository_root / "docker-compose.yml").read_text(encoding="utf-8"))
    relay = compose["services"]["room-event-relay"]
    makefile = (repository_root / "Makefile").read_text(encoding="utf-8")

    assert "engine.relay.main:app" in relay["command"]
    assert relay["restart"] == "unless-stopped"
    assert relay["stop_grace_period"] == "15s"
    assert "ROOM_EVENT_RELAY_DATABASE_URL" in relay["environment"]["DATABASE_URL"]
    assert "host.docker.internal:54322" in relay["environment"]["DATABASE_URL"]
    assert "host.docker.internal:host-gateway" in relay["extra_hosts"]
    assert "healthcheck" in relay
    assert "engine" not in relay.get("depends_on", [])
    assert "dev-relay:" in makefile
    assert "test-room-event-relay:" in makefile


async def _wait_for_relay_ready(app) -> None:
    for _ in range(100):
        if app.state.room_event_relay.status.ready:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("relay did not become ready")


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


def _asyncpg_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _seed_outbox_events(engine: AsyncEngine, *, count: int) -> SeededOutbox:
    now = datetime.now(UTC)
    script_id = f"room-event-relay-{uuid4().hex}"
    session_id = uuid4()
    event_ids = tuple(uuid4() for _ in range(count))
    outbox_ids = tuple(uuid4() for _ in range(count))
    command_ids = tuple(uuid4() for _ in range(count))

    async with engine.begin() as connection:
        await connection.execute(
            insert(script_packages).values(
                id=script_id,
                name="Room event relay test",
                version="1.0.0",
                config={},
                status="published",
                created_at=now,
                updated_at=now,
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
                mode="legacy_single",
                revision=count,
                event_head_sequence=count,
                created_at=now,
                updated_at=now,
            )
        )
        for index, (command_id, event_id, outbox_id) in enumerate(
            zip(command_ids, event_ids, outbox_ids, strict=True),
            start=1,
        ):
            await connection.execute(
                insert(session_command_receipts).values(
                    session_id=session_id,
                    command_id=command_id,
                    command_kind="multiplayer_v1",
                    request_payload={"sequence": index},
                    request_sha256=f"{index:064x}",
                    expected_revision=index - 1,
                    base_revision=index - 1,
                    result_revision=index,
                    status="succeeded",
                    result={"event_ids": []},
                    event_sequence_from=index,
                    event_sequence_to=index,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            await connection.execute(
                insert(session_events).values(
                    id=event_id,
                    session_id=session_id,
                    sequence=index,
                    revision=index,
                    command_id=command_id,
                    event_type="gameplay.command_succeeded",
                    event_version=1,
                    payload={"command_type": f"test.command.{index}"},
                    created_at=now,
                )
            )
            await connection.execute(
                insert(room_outbox).values(
                    id=outbox_id,
                    session_id=session_id,
                    room_event_id=event_id,
                    topic="room.events.v1",
                    available_at=datetime(1970, 1, 1, tzinfo=UTC),
                    created_at=now,
                    updated_at=now,
                )
            )

    return SeededOutbox(
        script_id=script_id,
        session_id=session_id,
        event_ids=event_ids,
        outbox_ids=outbox_ids,
    )


async def _remove_script(engine: AsyncEngine, script_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            delete(game_sessions).where(game_sessions.c.script_id == script_id)
        )
        await connection.execute(delete(script_packages).where(script_packages.c.id == script_id))
