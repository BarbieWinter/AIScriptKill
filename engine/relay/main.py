"""ASGI entry point for the independently supervised room-event relay."""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from engine.api.config import Settings, get_settings
from engine.db.session import SessionFactory, dispose_engine
from engine.services.room_event_relay import RoomEventRelay, RoomEventRelayConfig
from engine.services.room_event_transport import PostgresNotifyRoomOutboxPublisher
from engine.services.room_outbox import RoomOutboxPublisher

Dispose = Callable[[], Awaitable[None]]


def create_room_event_relay_app(
    *,
    settings: Settings | None = None,
    factory: async_sessionmaker[AsyncSession] = SessionFactory,
    publisher: RoomOutboxPublisher | None = None,
    dispose: Dispose = dispose_engine,
    worker_id: str | None = None,
) -> FastAPI:
    """Build an ASGI process that owns the relay lifecycle and health surface."""

    runtime_settings = settings or get_settings()
    runtime_publisher = publisher or PostgresNotifyRoomOutboxPublisher(
        factory,
        channel=runtime_settings.room_event_notify_channel,
    )
    relay = RoomEventRelay(
        factory,
        runtime_publisher,
        worker_id=worker_id or _default_worker_id(),
        config=RoomEventRelayConfig(
            batch_size=runtime_settings.room_event_relay_batch_size,
            poll_seconds=runtime_settings.room_event_relay_poll_seconds,
            lease_seconds=runtime_settings.room_event_relay_lease_seconds,
            publish_timeout_seconds=runtime_settings.room_event_relay_publish_timeout_seconds,
            retry_base_seconds=runtime_settings.room_event_relay_retry_base_seconds,
            retry_max_seconds=runtime_settings.room_event_relay_retry_max_seconds,
            max_attempts=runtime_settings.room_event_relay_max_attempts,
        ),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        stop = asyncio.Event()
        task: asyncio.Task[None] | None = None
        if runtime_settings.room_events_v1:
            task = asyncio.create_task(relay.run(stop), name="room-event-relay")
        try:
            yield
        finally:
            stop.set()
            if task is not None:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(task),
                        timeout=runtime_settings.room_event_relay_shutdown_grace_seconds,
                    )
                except TimeoutError:
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            await dispose()

    application = FastAPI(
        title="AI Script Kill Room Event Relay",
        version="1",
        lifespan=lifespan,
    )
    application.state.room_event_relay = relay

    async def live_health() -> dict[str, str | int]:
        return {"status": "ok", "service": "room-event-relay", "version": 1}

    async def ready_health() -> JSONResponse:
        if not runtime_settings.room_events_v1:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "running": False},
            )
        try:
            health = await relay.health()
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "not_ready", "running": relay.status.running},
            )
        ready = health.running and health.ready
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                **health.payload(),
            },
        )

    application.add_api_route("/health", live_health, methods=["GET"])
    application.add_api_route("/health/ready", ready_health, methods=["GET"])
    return application


def _default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"[:128]


app = create_room_event_relay_app()
