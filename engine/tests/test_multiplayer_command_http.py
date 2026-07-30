from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, ReadError, Request, Response
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from engine.api.main import create_app
from engine.api.middleware.auth import (
    CurrentUser,
    VerifiedAnonymousPrincipal,
    get_current_user,
    require_verified_anonymous_principal,
)
from engine.core.package_loader import load_package_directory
from engine.core.package_schema import ScriptPackageImport
from engine.core.runtime_package_snapshot import encode_runtime_package_snapshot
from engine.db.session import build_async_database_url, build_connect_args, get_db_session
from engine.db.tables import (
    game_sessions,
    room_character_assignments,
    room_members,
    room_outbox,
    room_principal_reservations,
    script_packages,
    session_command_receipts,
    session_events,
)
from engine.repositories.session_command_repository import SessionCommandRepository
from engine.services import multiplayer_room_service
from engine.services.room_outbox import RoomOutboxMessage, publish_room_outbox_batch

DATABASE_URL_ENV = "AISCRIPTKILL_MULTIPLAYER_COMMAND_DB_URL"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"


class DropResponseAfterCommitTransport(ASGITransport):
    async def handle_async_request(self, request: Request) -> Response:
        response = await super().handle_async_request(request)
        await response.aread()
        await response.aclose()
        raise ReadError("response lost after application commit", request=request)


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_identical_room_command_replays_one_durable_result_and_one_state_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-replay-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    member_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            replay = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            receipt_response = await client.get(
                f"/api/v1/sessions/{session_id}/commands/{command_id}"
            )
            snapshot_response = await client.get(f"/api/v1/sessions/{session_id}/snapshot")

        assert first.status_code == 200, first.text
        assert replay.status_code == 200
        assert receipt_response.status_code == 200, receipt_response.text
        first_result = first.json()
        replay_result = replay.json()
        assert first_result == {
            "command_id": str(command_id),
            "status": "accepted",
            "revision": 1,
            "event_sequence": 1,
            "result": {"event_ids": []},
            "error": None,
            "replayed": False,
        }
        assert replay_result == {**first_result, "replayed": True}
        assert receipt_response.json() == {
            "command_id": str(command_id),
            "status": "succeeded",
            "revision": 1,
            "event_sequence_from": 1,
            "event_sequence_to": 1,
            "result": first_result,
            "error_code": None,
            "error_details": {},
        }
        assert snapshot_response.status_code == 200
        lobby = snapshot_response.json()
        assert lobby["revision"] == 1
        assert lobby["self"]["character_id"] == "investigator"
        async with factory() as db:
            receipt = (
                (
                    await db.execute(
                        select(session_command_receipts).where(
                            session_command_receipts.c.session_id == session_id,
                            session_command_receipts.c.command_id == command_id,
                        )
                    )
                )
                .mappings()
                .one()
            )
            events = (
                (
                    await db.execute(
                        select(session_events).where(session_events.c.session_id == session_id)
                    )
                )
                .mappings()
                .all()
            )
            outbox = (
                (
                    await db.execute(
                        select(room_outbox).where(room_outbox.c.session_id == session_id)
                    )
                )
                .mappings()
                .all()
            )
            assignments = (
                await db.execute(
                    select(room_character_assignments.c.character_id).where(
                        room_character_assignments.c.session_id == session_id
                    )
                )
            ).all()
        assert receipt["status"] == "succeeded"
        assert receipt["actor_principal_id"] == principal_id
        assert receipt["actor_member_id"] == member_id
        assert receipt["event_sequence_from"] == 1
        assert receipt["event_sequence_to"] == 1
        assert len(events) == 1
        event = events[0]
        assert event["sequence"] == 1
        assert event["revision"] == 1
        assert event["command_id"] == command_id
        assert event["event_type"] == "lobby.command_succeeded"
        assert event["payload"] == {"command_type": "room.assign_character"}
        assert len(outbox) == 1
        pending = outbox[0]
        assert pending["session_id"] == session_id
        assert pending["room_event_id"] == event["id"]
        assert pending["topic"] == "room.events.v1"
        assert pending["attempts"] == 0
        assert pending["available_at"] is not None
        assert pending["published_at"] is None
        assert pending["last_error"] is None
        assert assignments == [("investigator",)]
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_stale_room_command_replays_one_durable_terminal_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-stale-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 1,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            replay = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            receipt_response = await client.get(
                f"/api/v1/sessions/{session_id}/commands/{command_id}"
            )
            snapshot_response = await client.get(f"/api/v1/sessions/{session_id}/snapshot")

        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        assert receipt_response.status_code == 200, receipt_response.text
        first_result = first.json()
        async with factory() as db:
            room_artifacts = (
                await db.execute(
                    select(
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                    ).where(game_sessions.c.id == session_id)
                )
            ).one()
            events = (
                await db.execute(
                    select(session_events.c.id).where(session_events.c.session_id == session_id)
                )
            ).all()
            outbox = (
                await db.execute(
                    select(room_outbox.c.id).where(room_outbox.c.session_id == session_id)
                )
            ).all()
        assert first_result == {
            "command_id": str(command_id),
            "status": "rejected",
            "revision": 0,
            "event_sequence": 0,
            "result": None,
            "error": {
                "code": "REVISION_MISMATCH",
                "message": "房间 revision 已变化，请刷新快照",
                "details": {"expected_revision": "1", "actual_revision": "0"},
            },
            "replayed": False,
        }
        assert replay.json() == {**first_result, "replayed": True}
        assert receipt_response.json() == {
            "command_id": str(command_id),
            "status": "rejected",
            "revision": 0,
            "event_sequence_from": None,
            "event_sequence_to": None,
            "result": None,
            "error_code": "REVISION_MISMATCH",
            "error_details": {
                "expected_revision": "1",
                "actual_revision": "0",
                "command_result": first_result,
            },
        }
        assert snapshot_response.status_code == 200
        lobby = snapshot_response.json()
        assert lobby["revision"] == 0
        assert lobby["self"]["character_id"] is None
        assert room_artifacts == (0, 0)
        assert events == []
        assert outbox == []
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_invalid_room_command_replays_one_durable_business_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-rejection-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "not-playable"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            replay = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            snapshot_response = await client.get(f"/api/v1/sessions/{session_id}/snapshot")

        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        first_result = first.json()
        async with factory() as db:
            room_artifacts = (
                await db.execute(
                    select(
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                    ).where(game_sessions.c.id == session_id)
                )
            ).one()
            events = (
                await db.execute(
                    select(session_events.c.id).where(session_events.c.session_id == session_id)
                )
            ).all()
            outbox = (
                await db.execute(
                    select(room_outbox.c.id).where(room_outbox.c.session_id == session_id)
                )
            ).all()
        assert first_result == {
            "command_id": str(command_id),
            "status": "rejected",
            "revision": 0,
            "event_sequence": 0,
            "result": None,
            "error": {
                "code": "CHARACTER_NOT_PLAYABLE",
                "message": "指定角色不可供玩家选择",
                "details": {},
            },
            "replayed": False,
        }
        assert replay.json() == {**first_result, "replayed": True}
        assert snapshot_response.status_code == 200
        lobby = snapshot_response.json()
        assert lobby["revision"] == 0
        assert lobby["self"]["character_id"] is None
        assert room_artifacts == (0, 0)
        assert events == []
        assert outbox == []
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_noop_room_command_writes_receipt_without_event_or_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-noop-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    member_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(room_character_assignments).values(
                session_id=session_id,
                member_id=member_id,
                character_id="investigator",
                assigned_at=now,
            )
        )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)

        assert response.status_code == 200, response.text
        assert response.json()["revision"] == 0
        assert response.json()["event_sequence"] == 0
        async with factory() as db:
            receipt = (
                (
                    await db.execute(
                        select(session_command_receipts).where(
                            session_command_receipts.c.session_id == session_id,
                            session_command_receipts.c.command_id == command_id,
                        )
                    )
                )
                .mappings()
                .one()
            )
            events = (
                await db.execute(
                    select(session_events.c.sequence).where(
                        session_events.c.session_id == session_id
                    )
                )
            ).all()
        assert receipt["status"] == "succeeded"
        assert receipt["event_sequence_from"] is None
        assert receipt["event_sequence_to"] is None
        assert events == []
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_staged_terminal_bundle_rolls_back_before_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-atomic-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    original = multiplayer_room_service.SessionCommandRepository.finalize_success

    async def fail_after_staging(
        repository: SessionCommandRepository,
        *,
        session_id: UUID,
        command_id: UUID,
        result: dict[str, object],
        revision: int,
        event_sequence: int | None,
        event_payload: dict[str, object] | None = None,
        event_type: str = "command_succeeded",
        attempt_count: int | None = None,
        checkpoint_id: str | None = None,
        state_sha256: str | None = None,
        outbox_topic: str | None = None,
    ) -> bool:
        finalized = await original(
            repository,
            session_id=session_id,
            command_id=command_id,
            result=result,
            revision=revision,
            event_sequence=event_sequence,
            event_payload=event_payload,
            event_type=event_type,
            attempt_count=attempt_count,
            checkpoint_id=checkpoint_id,
            state_sha256=state_sha256,
            outbox_topic=outbox_topic,
        )
        assert finalized is True
        raise RuntimeError("failure after terminal bundle staging")

    monkeypatch.setattr(
        multiplayer_room_service.SessionCommandRepository,
        "finalize_success",
        fail_after_staging,
    )
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            with pytest.raises(RuntimeError, match="failure after terminal bundle staging"):
                await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
        monkeypatch.setattr(
            multiplayer_room_service.SessionCommandRepository,
            "finalize_success",
            original,
        )
        async with factory() as db:
            room = (
                await db.execute(
                    select(
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                    ).where(game_sessions.c.id == session_id)
                )
            ).one()
            receipt = (
                await db.execute(
                    select(
                        session_command_receipts.c.status,
                        session_command_receipts.c.event_sequence_from,
                        session_command_receipts.c.event_sequence_to,
                    ).where(
                        session_command_receipts.c.session_id == session_id,
                        session_command_receipts.c.command_id == command_id,
                    )
                )
            ).one_or_none()
            outbox = (
                await db.execute(
                    select(room_outbox.c.id).where(room_outbox.c.session_id == session_id)
                )
            ).one_or_none()
            events = (
                await db.execute(
                    select(session_events.c.id).where(session_events.c.session_id == session_id)
                )
            ).all()
            assignment = (
                await db.execute(
                    select(room_character_assignments.c.character_id).where(
                        room_character_assignments.c.session_id == session_id
                    )
                )
            ).one_or_none()
        assert room == (0, 0)
        assert receipt == ("processing", None, None)
        assert events == []
        assert outbox is None
        assert assignment is None
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_other_room_member_cannot_replay_or_query_command_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-private-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    member_id = uuid4()
    other_principal_id = uuid4()
    other_member_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(room_members).values(
                id=other_member_id,
                session_id=session_id,
                principal_id=other_principal_id,
                room_role="player",
                membership_status="joined",
                ready_at=None,
                joined_at=now,
                left_at=None,
            )
        )
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, principal_id)),
            base_url="http://testserver",
        ) as owner_client:
            accepted = await owner_client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=command,
            )
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, other_principal_id)),
            base_url="http://testserver",
        ) as other_client:
            replay = await other_client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=command,
            )
            receipt = await other_client.get(f"/api/v1/sessions/{session_id}/commands/{command_id}")

        assert accepted.status_code == 200, accepted.text
        assert replay.status_code == 404, replay.text
        assert replay.json()["error"]["code"] == "COMMAND_NOT_FOUND"
        assert receipt.status_code == 404, receipt.text
        assert receipt.json()["error"]["code"] == "COMMAND_NOT_FOUND"
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_lobby_command_after_start_is_durable_terminal_rejection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-command-state-rejection-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    async with engine.begin() as connection:
        await connection.execute(
            update(game_sessions).where(game_sessions.c.id == session_id).values(status="active")
        )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
            replay = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)

        assert first.status_code == 200, first.text
        assert first.json()["status"] == "rejected"
        assert first.json()["error"]["code"] == "ROOM_NOT_IN_LOBBY"
        assert replay.status_code == 200, replay.text
        assert replay.json() == {**first.json(), "replayed": True}
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_expired_blocker_is_failed_and_different_command_is_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"command-poison-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    member_id = uuid4()
    blocker_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(session_command_receipts).values(
                session_id=session_id,
                command_id=blocker_id,
                actor_principal_id=principal_id,
                actor_member_id=member_id,
                command_kind="multiplayer_v1",
                request_payload={
                    "expected_revision": 0,
                    "type": "room.assign_character",
                    "payload": {"character_id": "insider"},
                },
                request_sha256="0" * 64,
                expected_revision=0,
                base_revision=0,
                status="processing",
                attempt_count=1,
                lease_expires_at=now - timedelta(seconds=1),
                created_at=now,
                updated_at=now,
            )
        )
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, principal_id)),
            base_url="http://testserver",
        ) as client:
            response = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"
        async with factory() as db:
            blocker = (
                await db.execute(
                    select(
                        session_command_receipts.c.status,
                        session_command_receipts.c.error_code,
                        session_command_receipts.c.lease_expires_at,
                    ).where(session_command_receipts.c.command_id == blocker_id)
                )
            ).one()
            assignments = (
                await db.execute(
                    select(room_character_assignments.c.character_id).where(
                        room_character_assignments.c.session_id == session_id
                    )
                )
            ).all()
            events = (
                await db.execute(
                    select(session_events.c.command_id).where(
                        session_events.c.session_id == session_id
                    )
                )
            ).all()
        assert blocker == ("failed", "COMMAND_SUPERSEDED", None)
        assert assignments == [("investigator",)]
        assert events == [(command_id,)]
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_cross_room_command_id_collision_is_rejected_without_receipt_disclosure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    command_id = uuid4()
    first_script_id = f"command-owner-{uuid4().hex}"
    second_script_id = f"command-collision-{uuid4().hex}"
    first_package = replace(package, package=replace(package.package, id=first_script_id))
    second_package = replace(package, package=replace(package.package, id=second_script_id))
    first_snapshot = encode_runtime_package_snapshot(first_package)
    second_snapshot = encode_runtime_package_snapshot(second_package)
    first_session_id = uuid4()
    second_session_id = uuid4()
    first_principal_id = uuid4()
    second_principal_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=first_script_id,
        session_id=first_session_id,
        principal_id=first_principal_id,
        member_id=uuid4(),
        package=first_package,
        snapshot_payload=dict(first_snapshot.payload),
        snapshot_sha256=first_snapshot.sha256,
    )
    await _seed_lobby(
        engine,
        script_id=second_script_id,
        session_id=second_session_id,
        principal_id=second_principal_id,
        member_id=uuid4(),
        package=second_package,
        snapshot_payload=dict(second_snapshot.payload),
        snapshot_sha256=second_snapshot.sha256,
    )
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, first_principal_id)),
            base_url="http://testserver",
        ) as owner:
            accepted = await owner.post(
                f"/api/v1/sessions/{first_session_id}/commands",
                json=command,
            )
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, second_principal_id)),
            base_url="http://testserver",
        ) as other:
            collision = await other.post(
                f"/api/v1/sessions/{second_session_id}/commands",
                json=command,
            )
            hidden = await other.get(f"/api/v1/sessions/{second_session_id}/commands/{command_id}")

        assert accepted.status_code == 200, accepted.text
        assert collision.status_code == 409, collision.text
        assert collision.json()["error"] == {
            "code": "COMMAND_ID_REUSED",
            "message": "command_id 已绑定到其他多人房间",
            "details": {},
        }
        assert str(first_session_id) not in collision.text
        assert str(first_principal_id) not in collision.text
        assert hidden.status_code == 404, hidden.text
        assert hidden.json()["error"]["code"] == "COMMAND_NOT_FOUND"
        async with factory() as db:
            first_events = (
                await db.execute(
                    select(session_events.c.id).where(
                        session_events.c.session_id == first_session_id
                    )
                )
            ).all()
            first_outbox = (
                await db.execute(
                    select(room_outbox.c.room_event_id).where(
                        room_outbox.c.session_id == first_session_id
                    )
                )
            ).all()
            second_room = (
                await db.execute(
                    select(
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                    ).where(game_sessions.c.id == second_session_id)
                )
            ).one()
            second_receipts = (
                await db.execute(
                    select(session_command_receipts.c.id).where(
                        session_command_receipts.c.session_id == second_session_id
                    )
                )
            ).all()
            second_events = (
                await db.execute(
                    select(session_events.c.id).where(
                        session_events.c.session_id == second_session_id
                    )
                )
            ).all()
            second_outbox = (
                await db.execute(
                    select(room_outbox.c.id).where(room_outbox.c.session_id == second_session_id)
                )
            ).all()
            second_assignments = (
                await db.execute(
                    select(room_character_assignments.c.character_id).where(
                        room_character_assignments.c.session_id == second_session_id
                    )
                )
            ).all()
        assert len(first_events) == 1
        assert first_outbox == first_events
        assert second_room == (0, 0)
        assert second_receipts == []
        assert second_events == []
        assert second_outbox == []
        assert second_assignments == []
    finally:
        await _remove_script(engine, first_script_id)
        await _remove_script(engine, second_script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_processing_receipt_get_returns_200_with_processing_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"processing-receipt-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    member_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(session_command_receipts).values(
                session_id=session_id,
                command_id=command_id,
                actor_principal_id=principal_id,
                actor_member_id=member_id,
                command_kind="multiplayer_v1",
                request_payload={"expected_revision": 0},
                request_sha256="0" * 64,
                expected_revision=0,
                base_revision=0,
                status="processing",
                attempt_count=1,
                lease_expires_at=now + timedelta(seconds=30),
                created_at=now,
                updated_at=now,
            )
        )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=_test_app(factory, principal_id)),
            base_url="http://testserver",
        ) as client:
            response = await client.get(f"/api/v1/sessions/{session_id}/commands/{command_id}")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "processing"
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_room_outbox_retries_delivery_with_stable_event_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-outbox-retry-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    command_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)
    command = {
        "command_id": str(command_id),
        "expected_revision": 0,
        "type": "room.assign_character",
        "payload": {"character_id": "investigator"},
    }

    class FlakyPublisher:
        def __init__(self) -> None:
            self.messages: list[RoomOutboxMessage] = []

        async def publish(self, message: RoomOutboxMessage) -> None:
            if message.session_id != session_id:
                raise RuntimeError("unrelated pending room event")
            self.messages.append(message)
            if len(self.messages) == 1:
                raise RuntimeError("broker unavailable")

    publisher = FlakyPublisher()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.post(f"/api/v1/sessions/{session_id}/commands", json=command)
        assert response.status_code == 200, response.text

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.session_id == session_id)
                .values(available_at=datetime(1900, 1, 1, tzinfo=UTC))
            )
        first = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="room-outbox-retry-first",
            limit=1,
        )

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.session_id == session_id)
                .values(available_at=datetime(1900, 1, 1, tzinfo=UTC))
            )

        second = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="room-outbox-retry-second",
            limit=1,
        )
        async with factory() as db:
            row = (
                (
                    await db.execute(
                        select(room_outbox).where(room_outbox.c.session_id == session_id)
                    )
                )
                .mappings()
                .one()
            )
        assert first.published == 0
        assert first.failed == 1
        assert second.published == 1
        assert second.failed == 0
        assert len(publisher.messages) == 2
        assert publisher.messages[0] == publisher.messages[1]
        assert publisher.messages[0].event_id == row["room_event_id"]
        assert publisher.messages[0].topic == "room.events.v1"
        assert publisher.messages[0].payload == {"command_type": "room.assign_character"}
        assert row["attempts"] == 2
        assert row["published_at"] is not None
        assert row["last_error"] is None
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_room_outbox_concurrent_claims_are_disjoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-outbox-concurrent-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    principal_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=principal_id,
        member_id=uuid4(),
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    app = _test_app(factory, principal_id)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            assign = await client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json={
                    "command_id": str(uuid4()),
                    "expected_revision": 0,
                    "type": "room.assign_character",
                    "payload": {"character_id": "investigator"},
                },
            )
            ready = await client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json={
                    "command_id": str(uuid4()),
                    "expected_revision": 1,
                    "type": "room.ready",
                    "payload": {"ready": True},
                },
            )
        assert assign.status_code == 200, assign.text
        assert ready.status_code == 200, ready.text

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.session_id == session_id)
                .values(available_at=datetime(1900, 1, 1, tzinfo=UTC))
            )

        class ConcurrentPublisher:
            def __init__(self) -> None:
                self.messages: list[RoomOutboxMessage] = []
                self.claims_ready = asyncio.Event()

            async def publish(self, message: RoomOutboxMessage) -> None:
                if message.session_id != session_id:
                    raise RuntimeError("unrelated pending room event")
                self.messages.append(message)
                if len(self.messages) == 2:
                    self.claims_ready.set()
                await asyncio.wait_for(self.claims_ready.wait(), timeout=2)

        publisher = ConcurrentPublisher()

        async def claim_one(worker_id: str) -> int:
            result = await publish_room_outbox_batch(
                factory,
                publisher,
                worker_id=worker_id,
                limit=1,
                publish_timeout_seconds=3,
            )
            return result.published

        claim_counts = await asyncio.wait_for(
            asyncio.gather(
                claim_one("room-outbox-concurrent-one"),
                claim_one("room-outbox-concurrent-two"),
            ),
            timeout=5,
        )

        async with factory() as db:
            rows = (
                (
                    await db.execute(
                        select(room_outbox)
                        .where(room_outbox.c.session_id == session_id)
                        .order_by(room_outbox.c.id)
                    )
                )
                .mappings()
                .all()
            )
        assert claim_counts == [1, 1]
        assert len(publisher.messages) == 2
        assert {message.event_id for message in publisher.messages} == {
            row["room_event_id"] for row in rows
        }
        assert all(row["attempts"] == 1 for row in rows)
        assert all(row["published_at"] is not None for row in rows)
        assert all(row["last_error"] is None for row in rows)
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_two_players_complete_gameplay_through_durable_http_commands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"gameplay-completion-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    host_principal_id = uuid4()
    guest_principal_id = uuid4()
    host_member_id = uuid4()
    guest_member_id = uuid4()
    await _seed_lobby(
        engine,
        script_id=script_id,
        session_id=session_id,
        principal_id=host_principal_id,
        member_id=host_member_id,
        package=package,
        snapshot_payload=dict(snapshot.payload),
        snapshot_sha256=snapshot.sha256,
    )
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(room_members).values(
                id=guest_member_id,
                session_id=session_id,
                principal_id=guest_principal_id,
                room_role="player",
                membership_status="joined",
                ready_at=None,
                joined_at=now + timedelta(milliseconds=1),
                left_at=None,
            )
        )
        await connection.execute(
            insert(room_principal_reservations).values(
                principal_id=guest_principal_id,
                session_id=session_id,
                member_id=guest_member_id,
                created_at=now,
            )
        )

    revision = 0
    sequence = 0
    command_ids: list[UUID] = []
    no_event_command_ids: list[UUID] = []
    secret_vote_command_ids: list[UUID] = []

    async def send_command(
        client: AsyncClient,
        command_type: str,
        payload: dict[str, object],
        *,
        changes_revision: bool = True,
        command_id: UUID | None = None,
    ) -> tuple[dict[str, object], UUID]:
        nonlocal revision, sequence
        resolved_command_id = command_id or uuid4()
        response = await client.post(
            f"/api/v1/sessions/{session_id}/commands",
            json={
                "command_id": str(resolved_command_id),
                "expected_revision": revision,
                "type": command_type,
                "payload": payload,
            },
        )
        assert response.status_code == 200, response.text
        body = cast(dict[str, object], response.json())
        assert body["status"] == "accepted"
        if changes_revision:
            revision += 1
        sequence += 1
        assert body["revision"] == revision
        assert body["event_sequence"] == sequence
        command_ids.append(resolved_command_id)
        return body, resolved_command_id

    try:
        async with (
            AsyncClient(
                transport=ASGITransport(app=_test_app(factory, host_principal_id)),
                base_url="http://testserver",
            ) as host,
            AsyncClient(
                transport=ASGITransport(app=_test_app(factory, guest_principal_id)),
                base_url="http://testserver",
            ) as guest,
        ):
            await send_command(
                host,
                "room.assign_character",
                {"character_id": "investigator"},
            )
            await send_command(
                guest,
                "room.assign_character",
                {"character_id": "insider"},
            )
            await send_command(host, "room.ready", {"ready": True})
            await send_command(guest, "room.ready", {"ready": True})
            await send_command(host, "room.start", {})

            host_snapshot_response = await host.get(f"/api/v1/sessions/{session_id}/snapshot")
            guest_snapshot_response = await guest.get(f"/api/v1/sessions/{session_id}/snapshot")
            assert host_snapshot_response.status_code == 200, host_snapshot_response.text
            assert guest_snapshot_response.status_code == 200, guest_snapshot_response.text
            host_snapshot = cast(dict[str, object], host_snapshot_response.json())
            guest_snapshot = cast(dict[str, object], guest_snapshot_response.json())
            assert host_snapshot["phase"] == "read"
            assert guest_snapshot["phase"] == "read"
            host_chapters = cast(list[dict[str, object]], host_snapshot["chapters"])
            guest_chapters = cast(list[dict[str, object]], guest_snapshot["chapters"])
            assert [chapter["id"] for chapter in host_chapters] == ["investigator-investigation"]
            assert [chapter["id"] for chapter in guest_chapters] == ["insider-investigation"]
            assert "private_by_member" not in host_snapshot_response.text
            assert "insider-investigation" not in host_snapshot_response.text
            assert "investigator-investigation" not in guest_snapshot_response.text
            assert "dm_guide" not in host_snapshot_response.text

            await send_command(
                host,
                "stage.confirm_read",
                {"stage_id": "investigation"},
            )
            noop_command_id = uuid4()
            noop_command = {
                "command_id": str(noop_command_id),
                "expected_revision": revision,
                "type": "stage.confirm_read",
                "payload": {"stage_id": "investigation"},
            }
            noop_first = await host.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=noop_command,
            )
            noop_replay = await host.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=noop_command,
            )
            assert noop_first.status_code == 200, noop_first.text
            noop_result = {
                "command_id": str(noop_command_id),
                "status": "accepted",
                "revision": revision,
                "event_sequence": 0,
                "result": {"event_ids": []},
                "error": None,
                "replayed": False,
            }
            assert noop_first.json() == noop_result
            assert noop_replay.status_code == 200, noop_replay.text
            assert noop_replay.json() == {**noop_result, "replayed": True}
            no_event_command_ids.append(noop_command_id)

            await send_command(
                guest,
                "stage.confirm_read",
                {"stage_id": "investigation"},
            )
            await send_command(
                host,
                "hint.request",
                {"hint_id": "timeline", "level": 1},
            )
            await send_command(
                guest,
                "hint.confirm",
                {"hint_id": "timeline", "level": 1},
            )
            message_id = uuid4()
            chat_command_id = uuid4()
            chat_payload: dict[str, object] = {
                "stage_id": "investigation",
                "message_id": str(message_id),
                "text": "门锁没有损坏。",
            }
            async with AsyncClient(
                transport=DropResponseAfterCommitTransport(
                    app=_test_app(factory, host_principal_id)
                ),
                base_url="http://testserver",
            ) as lossy_host:
                with pytest.raises(ReadError, match="response lost after application commit"):
                    await lossy_host.post(
                        f"/api/v1/sessions/{session_id}/commands",
                        json={
                            "command_id": str(chat_command_id),
                            "expected_revision": revision,
                            "type": "discussion.send_message",
                            "payload": chat_payload,
                        },
                    )
            async with factory() as db:
                committed_chat_event = (
                    await db.execute(
                        select(
                            session_events.c.id,
                            session_events.c.sequence,
                            session_events.c.revision,
                        ).where(
                            session_events.c.session_id == session_id,
                            session_events.c.command_id == chat_command_id,
                        )
                    )
                ).one()
                committed_chat_outbox = (
                    await db.execute(
                        select(
                            room_outbox.c.room_event_id,
                            room_outbox.c.topic,
                        ).where(
                            room_outbox.c.session_id == session_id,
                            room_outbox.c.room_event_id == committed_chat_event.id,
                        )
                    )
                ).one()
            assert committed_chat_event.sequence == sequence + 1
            assert committed_chat_event.revision == revision
            assert committed_chat_outbox == (committed_chat_event.id, "room.events.v1")
            committed_chat_event_id = committed_chat_event.id
            sequence += 1
            command_ids.append(chat_command_id)
            replay = await host.post(
                f"/api/v1/sessions/{session_id}/commands",
                json={
                    "command_id": str(chat_command_id),
                    "expected_revision": revision,
                    "type": "discussion.send_message",
                    "payload": chat_payload,
                },
            )
            assert replay.status_code == 200, replay.text
            assert replay.json() == {
                "command_id": str(chat_command_id),
                "status": "accepted",
                "revision": revision,
                "event_sequence": sequence,
                "result": {"event_ids": []},
                "error": None,
                "replayed": True,
            }

            guest_discussion_response = await guest.get(f"/api/v1/sessions/{session_id}/snapshot")
            assert guest_discussion_response.status_code == 200
            guest_discussion = cast(dict[str, object], guest_discussion_response.json())
            messages = cast(list[dict[str, object]], guest_discussion["discussion_messages"])
            assert messages == [
                {
                    "sequence": sequence,
                    "message_id": messages[0]["message_id"],
                    "stage_id": "investigation",
                    "member_id": str(host_member_id),
                    "character_id": "investigator",
                    "text": "门锁没有损坏。",
                }
            ]

            await send_command(
                host,
                "discussion.confirm_close",
                {"stage_id": "investigation"},
            )
            await send_command(
                host,
                "discussion.revoke_close",
                {"stage_id": "investigation"},
            )
            await send_command(
                host,
                "discussion.confirm_close",
                {"stage_id": "investigation"},
            )
            await send_command(
                guest,
                "discussion.confirm_close",
                {"stage_id": "investigation"},
            )
            _, host_vote_id = await send_command(
                host,
                "settlement.submit",
                {
                    "settlement_id": "investigation-vote",
                    "option_id": "investigator-account",
                },
            )
            secret_vote_command_ids.append(host_vote_id)

            guest_settle_response = await guest.get(f"/api/v1/sessions/{session_id}/snapshot")
            assert guest_settle_response.status_code == 200
            guest_settle = cast(dict[str, object], guest_settle_response.json())
            settlement = cast(dict[str, object], guest_settle["settlement"])
            assert settlement["own_option_id"] is None
            assert settlement["revealed"] is False
            assert settlement["revealed_ballots"] == []
            assert settlement["outcome_id"] is None

            _, guest_vote_id = await send_command(
                guest,
                "settlement.submit",
                {
                    "settlement_id": "investigation-vote",
                    "option_id": "insider-account",
                },
            )
            secret_vote_command_ids.append(guest_vote_id)
            reveal_response = await host.get(f"/api/v1/sessions/{session_id}/snapshot")
            assert reveal_response.status_code == 200
            reveal = cast(dict[str, object], reveal_response.json())
            assert reveal["phase"] == "reveal"
            assert reveal["can_advance"] is True
            revealed_settlement = cast(dict[str, object], reveal["settlement"])
            assert len(cast(list[object], revealed_settlement["revealed_ballots"])) == 2

            await send_command(
                host,
                "stage.advance",
                {"stage_id": "investigation"},
            )
            await send_command(
                host,
                "stage.confirm_read",
                {"stage_id": "final-judgment"},
            )
            await send_command(
                guest,
                "stage.confirm_read",
                {"stage_id": "final-judgment"},
            )
            await send_command(
                host,
                "discussion.confirm_close",
                {"stage_id": "final-judgment"},
            )
            await send_command(
                guest,
                "discussion.confirm_close",
                {"stage_id": "final-judgment"},
            )
            await send_command(
                host,
                "settlement.confirm_shared_choice",
                {
                    "settlement_id": "final-judgment",
                    "option_id": "timeline-conflict",
                },
            )
            await send_command(
                guest,
                "settlement.confirm_shared_choice",
                {
                    "settlement_id": "final-judgment",
                    "option_id": "timeline-conflict",
                },
            )

            for client, member_id in (
                (host, host_member_id),
                (guest, guest_member_id),
            ):
                completed_response = await client.get(f"/api/v1/sessions/{session_id}/snapshot")
                review_response = await client.get(f"/api/v1/sessions/{session_id}/review")
                current_response = await client.get("/api/v1/sessions/current")
                assert completed_response.status_code == 200
                completed = cast(dict[str, object], completed_response.json())
                assert completed["status"] == "completed"
                assert completed["ending_id"] == "conflicting-accounts"
                assert completed["revision"] == revision
                assert completed["event_head_sequence"] == sequence
                assert "private_by_member" not in completed_response.text
                assert review_response.status_code == 200, review_response.text
                review = cast(dict[str, object], review_response.json())
                assert review["member_id"] == str(member_id)
                assert cast(dict[str, object], review["ending"])["id"] == ("conflicting-accounts")
                assert "private_by_member" not in review_response.text
                assert '"ballots"' not in review_response.text
                assert current_response.status_code == 200
                assert current_response.json() is None

        async with engine.begin() as connection:
            await connection.execute(
                update(room_outbox)
                .where(room_outbox.c.session_id == session_id)
                .values(available_at=datetime(1900, 1, 1, tzinfo=UTC))
            )

        class CapturingPublisher:
            def __init__(self) -> None:
                self.messages: list[RoomOutboxMessage] = []

            async def publish(self, message: RoomOutboxMessage) -> None:
                if message.session_id != session_id:
                    raise RuntimeError("unrelated pending room event")
                self.messages.append(message)

        publisher = CapturingPublisher()
        batch = await publish_room_outbox_batch(
            factory,
            publisher,
            worker_id="gameplay-completion-outbox",
            limit=sequence,
        )
        async with factory() as db:
            room = (
                await db.execute(
                    select(
                        game_sessions.c.status,
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                        game_sessions.c.closed_at,
                    ).where(game_sessions.c.id == session_id)
                )
            ).one()
            events = (
                (
                    await db.execute(
                        select(session_events)
                        .where(session_events.c.session_id == session_id)
                        .order_by(session_events.c.sequence)
                    )
                )
                .mappings()
                .all()
            )
            receipts = (
                await db.execute(
                    select(
                        session_command_receipts.c.command_id,
                        session_command_receipts.c.status,
                        session_command_receipts.c.event_sequence_from,
                        session_command_receipts.c.event_sequence_to,
                    ).where(session_command_receipts.c.session_id == session_id)
                )
            ).all()
            reservations = (
                await db.execute(
                    select(room_principal_reservations.c.principal_id).where(
                        room_principal_reservations.c.session_id == session_id
                    )
                )
            ).all()
            outbox = (
                (
                    await db.execute(
                        select(room_outbox).where(room_outbox.c.session_id == session_id)
                    )
                )
                .mappings()
                .all()
            )

        assert room[0:3] == ("completed", revision, sequence)
        assert room.closed_at is not None
        assert [event["sequence"] for event in events] == list(range(1, sequence + 1))
        assert len(events) == len(command_ids)
        expected_receipt_ids = set(command_ids) | set(no_event_command_ids)
        assert len(receipts) == len(expected_receipt_ids)
        assert {receipt.command_id for receipt in receipts} == expected_receipt_ids
        assert {receipt.status for receipt in receipts} == {"succeeded"}
        noop_receipt = next(
            receipt for receipt in receipts if receipt.command_id == noop_command_id
        )
        assert noop_receipt.event_sequence_from is None
        assert noop_receipt.event_sequence_to is None
        assert reservations == []
        assert len(outbox) == len(events)
        assert {row["room_event_id"] for row in outbox} == {event["id"] for event in events}
        assert batch.published == sequence
        assert {row["topic"] for row in outbox} == {"room.events.v1"}
        assert all(row["published_at"] is not None for row in outbox)

        event_by_id = {event["id"]: event for event in events}
        replayed_chat_event = next(
            event for event in events if event["command_id"] == chat_command_id
        )
        assert replayed_chat_event["id"] == committed_chat_event_id
        assert sum(event["command_id"] == chat_command_id for event in events) == 1
        assert sum(row["room_event_id"] == committed_chat_event_id for row in outbox) == 1
        allowed_payload_keys = {
            "lobby.command_succeeded": {"command_type"},
            "discussion.message": {
                "message_id",
                "stage_id",
                "member_id",
                "character_id",
                "text",
            },
            "gameplay.command_succeeded": {
                "command_type",
                "stage_id",
                "actor_member_id",
            },
        }
        assert {message.event_id for message in publisher.messages} == set(event_by_id)
        for message in publisher.messages:
            event = event_by_id[message.event_id]
            assert message.topic == "room.events.v1"
            assert message.sequence == event["sequence"]
            assert message.revision == event["revision"]
            assert message.event_type == event["event_type"]
            assert message.event_version == event["event_version"]
            assert message.payload == event["payload"]
            assert set(message.payload) == allowed_payload_keys[message.event_type]

        serialized_payloads = json.dumps(
            [message.payload for message in publisher.messages],
            ensure_ascii=False,
            sort_keys=True,
        )
        for private_fact in (
            '"option_id"',
            '"own_option_id"',
            '"private_by_member"',
            '"private_state"',
            '"revealed_ballots"',
            "investigator-account",
            "insider-account",
            "dm_guide",
        ):
            assert private_fact not in serialized_payloads

        gameplay_command_types = {
            cast(dict[str, object], event["payload"])["command_type"]
            for event in events
            if event["event_type"] == "gameplay.command_succeeded"
        }
        assert gameplay_command_types == {
            "stage.confirm_read",
            "stage.advance",
            "discussion.confirm_close",
            "discussion.revoke_close",
            "settlement.submit",
            "settlement.confirm_shared_choice",
            "hint.request",
            "hint.confirm",
        }
        assert sum(event["event_type"] == "discussion.message" for event in events) == 1

        secret_events = [
            event for event in events if event["command_id"] in secret_vote_command_ids
        ]
        assert len(secret_events) == 2
        assert all(event["event_type"] == "gameplay.command_succeeded" for event in secret_events)
        assert all("option_id" not in event["payload"] for event in secret_events)
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


def _test_app(
    factory: async_sessionmaker[AsyncSession],
    principal_id: UUID,
) -> FastAPI:
    app = create_app()

    async def database_session() -> AsyncGenerator[AsyncSession]:
        async with factory() as db:
            try:
                yield db
            finally:
                if db.in_transaction():
                    await db.rollback()

    async def principal() -> VerifiedAnonymousPrincipal:
        return VerifiedAnonymousPrincipal(id=principal_id)

    async def current_user() -> CurrentUser:
        return CurrentUser(
            subject=str(principal_id),
            role="authenticated",
            is_anonymous=True,
        )

    app.dependency_overrides[get_db_session] = database_session
    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[require_verified_anonymous_principal] = principal
    return app


async def _seed_lobby(
    engine: AsyncEngine,
    *,
    script_id: str,
    session_id: UUID,
    principal_id: UUID,
    member_id: UUID,
    package: ScriptPackageImport,
    snapshot_payload: dict[str, object],
    snapshot_sha256: str,
) -> None:
    package_record = package.package
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(script_packages).values(
                id=script_id,
                name=package_record.title,
                version=package_record.version,
                config=package_record.config,
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
                player_character_id=None,
                state={},
                status="lobby",
                mode="multiplayer_v1",
                revision=0,
                event_head_sequence=0,
                state_schema_version=2,
                runtime_package_version=package_record.version,
                runtime_package_snapshot=snapshot_payload,
                runtime_package_sha256=snapshot_sha256,
                created_at=now,
                updated_at=now,
            )
        )
        await connection.execute(
            insert(room_members).values(
                id=member_id,
                session_id=session_id,
                principal_id=principal_id,
                room_role="host",
                membership_status="joined",
                ready_at=None,
                joined_at=now,
                left_at=None,
            )
        )
        await connection.execute(
            insert(room_principal_reservations).values(
                principal_id=principal_id,
                session_id=session_id,
                member_id=member_id,
                created_at=now,
            )
        )


async def _remove_script(engine: AsyncEngine, script_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            delete(game_sessions).where(game_sessions.c.script_id == script_id)
        )
        await connection.execute(delete(script_packages).where(script_packages.c.id == script_id))


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
