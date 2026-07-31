from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from hashlib import sha256
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from starlette.websockets import WebSocketDisconnect

import engine.services.room_stream_auth as room_stream_auth
from engine.api.main import create_app
from engine.api.middleware.auth import (
    VerifiedAnonymousPrincipal,
    require_verified_anonymous_principal,
)
from engine.db.session import build_async_database_url, build_connect_args, get_db_session
from engine.db.tables import (
    game_sessions,
    room_members,
    room_stream_tickets,
    script_packages,
)

DATABASE_URL_ENV = "AISCRIPTKILL_MULTIPLAYER_COMMAND_DB_URL"
TRUSTED_ORIGIN = "http://localhost:3000"


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_room_stream_ticket_lifecycle_and_membership_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(room_stream_auth, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_stream_auth,
        "get_settings",
        lambda: SimpleNamespace(multiplayer_v1=True, room_events_v1=True),
    )
    engine = create_async_engine(
        build_async_database_url(os.environ[DATABASE_URL_ENV]),
        connect_args=build_connect_args(os.environ[DATABASE_URL_ENV]),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-stream-{uuid4().hex}"
    principal_id = uuid4()
    member_id = uuid4()
    room_id = uuid4()
    other_room_id = uuid4()
    await _seed_rooms(
        factory,
        script_id=script_id,
        principal_id=principal_id,
        member_id=member_id,
        room_id=room_id,
        other_room_id=other_room_id,
    )
    app = _test_app(factory, principal_id)

    try:
        with TestClient(app) as client:
            first = _issue_ticket(client, room_id)
            await _assert_ticket_stored_as_digest(factory, room_id, member_id, first)
            _assert_ready(client, room_id, member_id, first)
            _assert_rejected(client, room_id, first)

            revoked = _issue_ticket(client, room_id)
            replacement = _issue_ticket(client, room_id)
            _assert_rejected(client, room_id, revoked)
            _assert_ready(client, room_id, member_id, replacement)

            concurrent = _issue_ticket(client, room_id)
            concurrent_outcomes = await asyncio.gather(
                _consume_ticket(factory, room_id, concurrent),
                _consume_ticket(factory, room_id, concurrent),
            )
            assert sorted(outcome[0] for outcome in concurrent_outcomes) == [
                "accepted",
                "rejected",
            ]
            assert sum(outcome[1] == member_id for outcome in concurrent_outcomes) == 1

            cross_room = _issue_ticket(client, room_id)
            _assert_rejected(client, other_room_id, cross_room)
            _assert_ready(client, room_id, member_id, cross_room)

            expired = _issue_ticket(client, room_id)
            async with factory() as db:
                await db.execute(
                    update(room_stream_tickets)
                    .where(
                        room_stream_tickets.c.session_id == room_id,
                        room_stream_tickets.c.member_id == member_id,
                        room_stream_tickets.c.consumed_at.is_(None),
                        room_stream_tickets.c.revoked_at.is_(None),
                    )
                    .values(expires_at=func.now())
                )
                await db.commit()
            _assert_rejected(client, room_id, expired)

            departed = _issue_ticket(client, room_id)
            async with factory() as db:
                await db.execute(
                    update(room_members)
                    .where(room_members.c.id == member_id)
                    .values(membership_status="left", left_at=func.now())
                )
                await db.commit()
            _assert_rejected(client, room_id, departed)
    finally:
        await _cleanup(factory, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_stream_ticket_issuance_hides_missing_room_from_outsider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(room_stream_auth, "require_multiplayer_enabled", lambda: None)
    monkeypatch.setattr(
        room_stream_auth,
        "get_settings",
        lambda: SimpleNamespace(multiplayer_v1=True, room_events_v1=True),
    )
    engine = create_async_engine(
        build_async_database_url(os.environ[DATABASE_URL_ENV]),
        connect_args=build_connect_args(os.environ[DATABASE_URL_ENV]),
        poolclass=NullPool,
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-stream-enumeration-{uuid4().hex}"
    principal_id = uuid4()
    member_id = uuid4()
    room_id = uuid4()
    other_room_id = uuid4()
    await _seed_rooms(
        factory,
        script_id=script_id,
        principal_id=principal_id,
        member_id=member_id,
        room_id=room_id,
        other_room_id=other_room_id,
    )

    try:
        outsider = _test_app(factory, uuid4())
        with TestClient(outsider) as client:
            inaccessible = client.post(f"/api/v1/sessions/{room_id}/stream-ticket")
            missing = client.post(f"/api/v1/sessions/{uuid4()}/stream-ticket")

        assert inaccessible.status_code == 404
        assert missing.status_code == 404
        assert inaccessible.json() == missing.json()
        assert inaccessible.json()["error"]["code"] == "ROOM_STREAM_UNAVAILABLE"
    finally:
        await _cleanup(factory, script_id)
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

    app.dependency_overrides[get_db_session] = database_session
    app.dependency_overrides[require_verified_anonymous_principal] = principal
    return app


def _issue_ticket(client: TestClient, room_id: UUID) -> str:
    response = client.post(f"/api/v1/sessions/{room_id}/stream-ticket")
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["protocol_version"] == 1
    return str(payload["ticket"])


async def _assert_ticket_stored_as_digest(
    factory: async_sessionmaker[AsyncSession],
    room_id: UUID,
    member_id: UUID,
    ticket: str,
) -> None:
    async with factory() as db:
        stored_hash = (
            await db.execute(
                room_stream_tickets.select()
                .with_only_columns(room_stream_tickets.c.ticket_hash)
                .where(
                    room_stream_tickets.c.session_id == room_id,
                    room_stream_tickets.c.member_id == member_id,
                    room_stream_tickets.c.consumed_at.is_(None),
                    room_stream_tickets.c.revoked_at.is_(None),
                )
            )
        ).scalar_one()

    assert stored_hash == sha256(ticket.encode("utf-8")).digest()
    assert stored_hash != ticket.encode("utf-8")


def _assert_ready(client: TestClient, room_id: UUID, member_id: UUID, ticket: str) -> None:
    with client.websocket_connect(
        f"/api/v1/ws/{room_id}",
        headers={"origin": TRUSTED_ORIGIN},
    ) as websocket:
        websocket.send_json(
            {
                "type": "connection.hello",
                "data": {"protocol_version": 1, "ticket": ticket},
            }
        )
        assert websocket.receive_json() == {
            "type": "connection.ready",
            "data": {
                "protocol_version": 1,
                "session_id": str(room_id),
                "member_id": str(member_id),
                "revision": 0,
                "event_head_sequence": 0,
            },
        }


async def _consume_ticket(
    factory: async_sessionmaker[AsyncSession],
    room_id: UUID,
    ticket: str,
) -> tuple[str, UUID | None]:
    async with factory() as db:
        try:
            stream = await room_stream_auth.consume_room_stream_ticket(
                room_id,
                ticket,
                1,
                db,
            )
        except room_stream_auth.RoomStreamAuthorizationError:
            return ("rejected", None)
        return ("accepted", stream.member_id)


def _assert_rejected(client: TestClient, room_id: UUID, ticket: str) -> None:
    with client.websocket_connect(
        f"/api/v1/ws/{room_id}",
        headers={"origin": TRUSTED_ORIGIN},
    ) as websocket:
        websocket.send_json(
            {
                "type": "connection.hello",
                "data": {"protocol_version": 1, "ticket": ticket},
            }
        )
        with pytest.raises(WebSocketDisconnect) as disconnect_info:
            websocket.receive_json()
    assert disconnect_info.value.code == 1008
    assert disconnect_info.value.reason == "Room stream authorization failed"


async def _seed_rooms(
    factory: async_sessionmaker[AsyncSession],
    *,
    script_id: str,
    principal_id: UUID,
    member_id: UUID,
    room_id: UUID,
    other_room_id: UUID,
) -> None:
    async with factory() as db:
        await db.execute(
            insert(script_packages).values(
                id=script_id,
                name="Room Stream Test",
                version="1.0.0",
                config={},
                status="published",
                created_at=func.now(),
                updated_at=func.now(),
            )
        )
        for session_id in (room_id, other_room_id):
            await db.execute(
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
                    runtime_package_version="1.0.0",
                    runtime_package_snapshot={},
                    runtime_package_sha256="0" * 64,
                    created_at=func.now(),
                    updated_at=func.now(),
                )
            )
        await db.execute(
            insert(room_members).values(
                id=member_id,
                session_id=room_id,
                principal_id=principal_id,
                room_role="host",
                membership_status="joined",
                ready_at=None,
                joined_at=func.now(),
                left_at=None,
            )
        )
        await db.commit()


async def _cleanup(factory: async_sessionmaker[AsyncSession], script_id: str) -> None:
    async with factory() as db:
        room_ids = (
            (
                await db.execute(
                    game_sessions.select()
                    .with_only_columns(game_sessions.c.id)
                    .where(game_sessions.c.script_id == script_id)
                )
            )
            .scalars()
            .all()
        )
        if room_ids:
            await db.execute(
                delete(room_stream_tickets).where(room_stream_tickets.c.session_id.in_(room_ids))
            )
            await db.execute(delete(room_members).where(room_members.c.session_id.in_(room_ids)))
            await db.execute(delete(game_sessions).where(game_sessions.c.id.in_(room_ids)))
        await db.execute(delete(script_packages).where(script_packages.c.id == script_id))
        await db.commit()
