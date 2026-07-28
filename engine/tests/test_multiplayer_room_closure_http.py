from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Literal, cast
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, insert, select
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
from engine.contracts.multiplayer_v1.state import (
    GAME_STATE_SCHEMA_VERSION,
    GameStateV2,
    PlayerState,
    PrivatePlayerState,
    RoomState,
)
from engine.contracts.multiplayer_v1.vocabulary import RoomStatus
from engine.core.multiplayer_state_machine import initialize_stage_runtime
from engine.core.package_loader import load_package_directory
from engine.core.package_multiplayer import multiplayer_stage_contract
from engine.core.runtime_package_snapshot import encode_runtime_package_snapshot
from engine.db.session import build_async_database_url, build_connect_args, get_db_session
from engine.db.tables import (
    game_sessions,
    room_invites,
    room_members,
    room_outbox,
    room_principal_reservations,
    script_packages,
    session_command_receipts,
    session_events,
)
from engine.repositories.package_import_repository import PackageImportRepository
from engine.services import multiplayer_room_service

DATABASE_URL_ENV = "AISCRIPTKILL_MULTIPLAYER_COMMAND_DB_URL"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "script-packages" / "mp1-two-player"


@pytest.mark.parametrize("initial_status", ("lobby", "active"))
@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_host_durably_closes_incomplete_room_and_releases_both_identities(
    monkeypatch: pytest.MonkeyPatch,
    initial_status: Literal["lobby", "active"],
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-close-{initial_status}-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    host_principal_id = uuid4()
    guest_principal_id = uuid4()
    host_member_id = uuid4()
    guest_member_id = uuid4()
    guest_command_id = uuid4()
    close_command_id = uuid4()
    old_invite_token = f"old-invite-{uuid4().hex}"

    await _install_package(factory, package)
    await _seed_room(
        engine,
        script_id=script_id,
        session_id=session_id,
        status=initial_status,
        host_principal_id=host_principal_id,
        guest_principal_id=guest_principal_id,
        host_member_id=host_member_id,
        guest_member_id=guest_member_id,
        package_snapshot=dict(snapshot.payload),
        package_sha256=snapshot.sha256,
        old_invite_token=old_invite_token,
        package=package,
    )
    host_app = _test_app(factory, host_principal_id)
    guest_app = _test_app(factory, guest_principal_id)

    try:
        guest_command = {
            "command_id": str(guest_command_id),
            "expected_revision": 3,
            "type": "room.end_incomplete",
            "payload": {"reason": "guest cannot close"},
        }
        close_command = {
            "command_id": str(close_command_id),
            "expected_revision": 3,
            "type": "room.end_incomplete",
            "payload": {"reason": "host ended incomplete room"},
        }
        async with (
            AsyncClient(
                transport=ASGITransport(app=host_app),
                base_url="http://testserver",
            ) as host,
            AsyncClient(
                transport=ASGITransport(app=guest_app),
                base_url="http://testserver",
            ) as guest,
        ):
            guest_rejection = await guest.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=guest_command,
            )
            first = await host.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=close_command,
            )
            replay = await host.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=close_command,
            )

            assert guest_rejection.status_code == 200, guest_rejection.text
            assert guest_rejection.json()["error"]["code"] == "HOST_REQUIRED"
            assert first.status_code == 200, first.text
            first_result = first.json()
            assert first_result == {
                "command_id": str(close_command_id),
                "status": "accepted",
                "revision": 4,
                "event_sequence": 3,
                "result": {"event_ids": []},
                "error": None,
                "replayed": False,
            }
            assert replay.status_code == 200
            assert replay.json() == {**first_result, "replayed": True}

            for client, member_id in ((host, host_member_id), (guest, guest_member_id)):
                closed_response = await client.get(f"/api/v1/sessions/{session_id}/snapshot")
                current_response = await client.get("/api/v1/sessions/current")
                review_response = await client.get(f"/api/v1/sessions/{session_id}/review")
                assert closed_response.status_code == 200, closed_response.text
                assert closed_response.json() == {
                    "session_id": str(session_id),
                    "mode": "multiplayer_v1",
                    "status": "closed",
                    "revision": 4,
                    "event_head_sequence": 3,
                    "package": {
                        "script_id": script_id,
                        "title": package.package.title,
                        "version": package.package.version,
                    },
                    "self_member_id": str(member_id),
                    "closed_at": closed_response.json()["closed_at"],
                    "review_available": False,
                }
                assert closed_response.json()["closed_at"] is not None
                assert "stage" not in closed_response.text
                assert "ending" not in closed_response.text
                assert "truth" not in closed_response.text
                assert current_response.status_code == 200
                assert current_response.json() is None
                assert review_response.status_code == 409
                assert review_response.json()["error"]["code"] == "REVIEW_NOT_AVAILABLE"

            blocked = await guest.post(
                f"/api/v1/sessions/{session_id}/commands",
                json={
                    "command_id": str(uuid4()),
                    "expected_revision": 4,
                    "type": "stage.confirm_read",
                    "payload": {"stage_id": "investigation"},
                },
            )
            assert blocked.status_code == 200
            assert blocked.json()["status"] == "rejected"
            assert blocked.json()["error"]["code"] == "ROOM_CLOSED"

            presence = await guest.put(
                f"/api/v1/sessions/{session_id}/scene-presence",
                json={"x": 945, "y": 970, "facing": "right", "moving": False},
            )
            assert presence.status_code == 409
            assert presence.json()["error"]["code"] == "ROOM_NOT_ACTIVE"

            recreated = await host.post(
                "/api/v1/sessions",
                json={"mode": "multiplayer_v1", "script_id": script_id},
            )
            assert recreated.status_code == 201, recreated.text
            next_session_id = recreated.json()["session_id"]
            invite = await host.post(
                f"/api/v1/sessions/{next_session_id}/invites",
                json={"ttl_seconds": 900},
            )
            assert invite.status_code == 201, invite.text
            accepted = await guest.post(f"/api/v1/session-invites/{invite.json()['token']}/accept")
            assert accepted.status_code == 200, accepted.text

        async with factory() as db:
            room = (
                await db.execute(
                    select(
                        game_sessions.c.status,
                        game_sessions.c.revision,
                        game_sessions.c.event_head_sequence,
                        game_sessions.c.state,
                        game_sessions.c.closed_at,
                    ).where(game_sessions.c.id == session_id)
                )
            ).one()
            reservations = (
                await db.execute(
                    select(room_principal_reservations.c.principal_id).where(
                        room_principal_reservations.c.session_id == session_id
                    )
                )
            ).all()
            old_invite = (
                await db.execute(
                    select(room_invites.c.revoked_at).where(room_invites.c.session_id == session_id)
                )
            ).one()
            events = (
                (
                    await db.execute(
                        select(session_events).where(session_events.c.session_id == session_id)
                    )
                )
                .mappings()
                .all()
            )
            receipts = (
                (
                    await db.execute(
                        select(session_command_receipts).where(
                            session_command_receipts.c.session_id == session_id
                        )
                    )
                )
                .mappings()
                .all()
            )
            outbox = (
                await db.execute(
                    select(room_outbox.c.id).where(room_outbox.c.session_id == session_id)
                )
            ).all()

        assert room.status == "closed"
        assert room.revision == 4
        assert room.event_head_sequence == 3
        assert room.closed_at is not None
        assert reservations == []
        assert old_invite.revoked_at is not None
        assert len(events) == 1
        assert events[0]["sequence"] == 3
        assert events[0]["revision"] == 4
        assert events[0]["command_id"] == close_command_id
        assert events[0]["event_type"] == "room.incomplete_closed"
        assert events[0]["payload"] == {
            "command_type": "room.end_incomplete",
            "previous_status": initial_status,
            "reason": "host ended incomplete room",
        }
        assert len(outbox) == 1
        assert {receipt["command_id"] for receipt in receipts} >= {
            guest_command_id,
            close_command_id,
        }
        close_receipt = next(
            receipt for receipt in receipts if receipt["command_id"] == close_command_id
        )
        assert close_receipt["status"] == "succeeded"
        assert close_receipt["event_sequence_from"] == 3
        assert close_receipt["event_sequence_to"] == 3
        if initial_status == "active":
            state = cast(dict[str, object], room.state)
            assert cast(dict[str, object], state["room"])["status"] == "closed"
            assert state["room_revision"] == 4
            assert state["ending_id"] is None
            stage = cast(dict[str, object], state["stage"])
            assert stage["read_member_ids"] == []
            assert stage["discussion_close_member_ids"] == []
        else:
            assert room.state == {}
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


@pytest.mark.skipif(
    os.getenv(DATABASE_URL_ENV) is None,
    reason=f"requires {DATABASE_URL_ENV} pointing to a disposable migrated PostgreSQL database",
)
async def test_completed_room_durably_rejects_end_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(multiplayer_room_service, "require_multiplayer_enabled", lambda: None)
    engine = _database_engine(_required_database_url())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    script_id = f"room-close-completed-{uuid4().hex}"
    package = load_package_directory(PACKAGE_ROOT, publish=True)
    package = replace(package, package=replace(package.package, id=script_id))
    snapshot = encode_runtime_package_snapshot(package)
    session_id = uuid4()
    host_principal_id = uuid4()
    host_member_id = uuid4()

    await _install_package(factory, package)
    now = datetime.now(UTC)
    async with engine.begin() as connection:
        await connection.execute(
            insert(game_sessions).values(
                id=session_id,
                script_id=script_id,
                player_id=None,
                player_character_id=None,
                state={},
                status="completed",
                mode="multiplayer_v1",
                revision=8,
                event_head_sequence=7,
                state_schema_version=2,
                runtime_package_version=package.package.version,
                runtime_package_snapshot=dict(snapshot.payload),
                runtime_package_sha256=snapshot.sha256,
                created_at=now,
                updated_at=now,
                closed_at=now,
            )
        )
        await connection.execute(
            insert(room_members).values(
                id=host_member_id,
                session_id=session_id,
                principal_id=host_principal_id,
                room_role="host",
                membership_status="joined",
                ready_at=now,
                joined_at=now,
                left_at=None,
            )
        )

    app = _test_app(factory, host_principal_id)
    command_id = uuid4()
    command = {
        "command_id": str(command_id),
        "expected_revision": 8,
        "type": "room.end_incomplete",
        "payload": {"reason": "must not replace completion"},
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            first = await client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=command,
            )
            replay = await client.post(
                f"/api/v1/sessions/{session_id}/commands",
                json=command,
            )
        assert first.status_code == 200, first.text
        assert first.json()["status"] == "rejected"
        assert first.json()["error"]["code"] == "ROOM_ALREADY_COMPLETED"
        assert replay.json() == {**first.json(), "replayed": True}

        async with factory() as db:
            room = (
                await db.execute(
                    select(
                        game_sessions.c.status,
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
        assert room == ("completed", 8, 7)
        assert events == []
        assert receipt["status"] == "rejected"
        assert receipt["error_code"] == "ROOM_ALREADY_COMPLETED"
    finally:
        await _remove_script(engine, script_id)
        await engine.dispose()


async def _install_package(factory: async_sessionmaker[AsyncSession], package) -> None:
    async with factory() as db:
        await PackageImportRepository(db).import_package(package)


async def _seed_room(
    engine: AsyncEngine,
    *,
    script_id: str,
    session_id: UUID,
    status: Literal["lobby", "active"],
    host_principal_id: UUID,
    guest_principal_id: UUID,
    host_member_id: UUID,
    guest_member_id: UUID,
    package_snapshot: dict[str, object],
    package_sha256: str,
    old_invite_token: str,
    package,
) -> None:
    now = datetime.now(UTC)
    state: dict[str, object] = {}
    if status == "active":
        definition = multiplayer_stage_contract(package, "investigation")
        member_ids = (str(host_member_id), str(guest_member_id))
        characters = ("investigator", "insider")
        game_state = GameStateV2(
            state_schema_version=GAME_STATE_SCHEMA_VERSION,
            session_id=session_id,
            room_revision=3,
            room=RoomState(
                status=RoomStatus.ACTIVE,
                required_member_ids=member_ids,
                current_stage_id=definition.id,
            ),
            players={
                member_id: PlayerState(
                    member_id=member_id,
                    character_id=character_id,
                    ready=True,
                )
                for member_id, character_id in zip(member_ids, characters, strict=True)
            },
            private_by_member={
                member_id: PrivatePlayerState(
                    character_id=character_id,
                    unlocked_chapter_ids=(definition.chapters[character_id],),
                )
                for member_id, character_id in zip(member_ids, characters, strict=True)
            },
            stage=initialize_stage_runtime(definition, required_member_ids=member_ids),
        )
        state = game_state.model_dump(mode="json")

    async with engine.begin() as connection:
        await connection.execute(
            insert(game_sessions).values(
                id=session_id,
                script_id=script_id,
                player_id=None,
                player_character_id=None,
                state=state,
                status=status,
                mode="multiplayer_v1",
                revision=3,
                event_head_sequence=2,
                state_schema_version=2,
                runtime_package_version=package.package.version,
                runtime_package_snapshot=package_snapshot,
                runtime_package_sha256=package_sha256,
                created_at=now,
                updated_at=now,
                started_at=now if status == "active" else None,
            )
        )
        await connection.execute(
            insert(room_members),
            [
                {
                    "id": host_member_id,
                    "session_id": session_id,
                    "principal_id": host_principal_id,
                    "room_role": "host",
                    "membership_status": "joined",
                    "ready_at": now,
                    "joined_at": now,
                    "left_at": None,
                },
                {
                    "id": guest_member_id,
                    "session_id": session_id,
                    "principal_id": guest_principal_id,
                    "room_role": "player",
                    "membership_status": "joined",
                    "ready_at": now,
                    "joined_at": now + timedelta(milliseconds=1),
                    "left_at": None,
                },
            ],
        )
        await connection.execute(
            insert(room_principal_reservations),
            [
                {
                    "principal_id": host_principal_id,
                    "session_id": session_id,
                    "member_id": host_member_id,
                    "created_at": now,
                },
                {
                    "principal_id": guest_principal_id,
                    "session_id": session_id,
                    "member_id": guest_member_id,
                    "created_at": now,
                },
            ],
        )
        await connection.execute(
            insert(room_invites).values(
                id=uuid4(),
                session_id=session_id,
                created_by_member_id=host_member_id,
                token_hash=sha256(old_invite_token.encode("utf-8")).digest(),
                expires_at=now + timedelta(minutes=15),
                max_uses=1,
                uses_count=0,
                revoked_at=None,
                created_at=now,
            )
        )


def _test_app(
    factory: async_sessionmaker[AsyncSession],
    principal_id: UUID,
) -> FastAPI:
    app = create_app()

    async def database_session():
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
