"""Authenticated, resource-bounded room WebSocket transport."""

import asyncio
import json
from collections import defaultdict, deque
from threading import Lock
from time import monotonic
from typing import Final, cast
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from engine.api.config import get_settings
from engine.contracts.multiplayer_v1.websocket import (
    CLIENT_FRAME_ADAPTER,
    ConnectionHelloFrame,
    ConnectionReadyData,
    ConnectionReadyFrame,
    SessionPingFrame,
)
from engine.db.session import SessionDep
from engine.services.room_stream_auth import (
    AuthenticatedRoomStream,
    RoomStreamAuthorizationError,
    consume_room_stream_ticket,
)

MAX_WEBSOCKET_CONNECTIONS: Final = 100
MAX_WEBSOCKET_CONNECTIONS_PER_CLIENT: Final = 4
MAX_WEBSOCKET_MESSAGE_BYTES: Final = 64 * 1024
MAX_WEBSOCKET_MESSAGES_PER_MINUTE: Final = 30
WEBSOCKET_IDLE_TIMEOUT_SECONDS: Final = 60.0

router = APIRouter(tags=["websocket"])


class _ConnectionRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._total = 0
        self._by_client: defaultdict[str, int] = defaultdict(int)

    def acquire(self, client: str) -> bool:
        with self._lock:
            if self._total >= MAX_WEBSOCKET_CONNECTIONS:
                return False
            if self._by_client[client] >= MAX_WEBSOCKET_CONNECTIONS_PER_CLIENT:
                return False
            self._total += 1
            self._by_client[client] += 1
            return True

    def release(self, client: str) -> None:
        with self._lock:
            self._total = max(self._total - 1, 0)
            remaining = self._by_client[client] - 1
            if remaining <= 0:
                self._by_client.pop(client, None)
            else:
                self._by_client[client] = remaining


_CONNECTIONS = _ConnectionRegistry()


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: UUID, db: SessionDep) -> None:
    """Authenticate one room membership before exposing ready or heartbeat frames."""

    if not _origin_allowed(websocket):
        await websocket.close(code=1008, reason="Room stream authorization failed")
        return

    client = websocket.client.host if websocket.client is not None else "unknown"
    if not _CONNECTIONS.acquire(client):
        await websocket.close(code=1013, reason="WebSocket capacity exceeded")
        return

    try:
        request_times: deque[float] = deque()
        authenticated: AuthenticatedRoomStream | None = None
        await websocket.accept()
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive(),
                    timeout=WEBSOCKET_IDLE_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                await websocket.close(code=1001, reason="WebSocket idle timeout")
                return
            if message["type"] == "websocket.disconnect":
                return
            raw_text = cast(object, message.get("text"))
            if not isinstance(raw_text, str):
                await websocket.close(code=1003, reason="WebSocket message must be text")
                return
            if len(raw_text.encode("utf-8")) > MAX_WEBSOCKET_MESSAGE_BYTES:
                await websocket.close(code=1009, reason="WebSocket message too large")
                return
            if not _within_message_rate(request_times):
                await websocket.close(code=1008, reason="WebSocket message rate exceeded")
                return
            try:
                frame = CLIENT_FRAME_ADAPTER.validate_json(raw_text)
            except (ValidationError, json.JSONDecodeError):
                await websocket.close(code=1003, reason="WebSocket message must match protocol")
                return

            if authenticated is None:
                if not isinstance(frame, ConnectionHelloFrame):
                    await websocket.close(code=1008, reason="Room stream authorization failed")
                    return
                try:
                    authenticated = await consume_room_stream_ticket(
                        session_id,
                        frame.data.ticket,
                        frame.data.protocol_version,
                        db,
                    )
                except RoomStreamAuthorizationError:
                    await websocket.close(code=1008, reason="Room stream authorization failed")
                    return
                ready = ConnectionReadyFrame(
                    type="connection.ready",
                    data=ConnectionReadyData(
                        protocol_version=1,
                        session_id=authenticated.session_id,
                        member_id=str(authenticated.member_id),
                        revision=authenticated.revision,
                        event_head_sequence=authenticated.event_head_sequence,
                    ),
                )
                await websocket.send_json(ready.model_dump(mode="json"))
                continue

            if isinstance(frame, SessionPingFrame):
                await websocket.send_json(
                    {"type": "session.pong", "data": {"session_id": str(authenticated.session_id)}},
                )
    except WebSocketDisconnect:
        return
    finally:
        _CONNECTIONS.release(client)


def _origin_allowed(websocket: WebSocket) -> bool:
    origin = websocket.headers.get("origin")
    allowed = get_settings().cors_origins
    return origin is not None and (origin in allowed or "*" in allowed)


def _within_message_rate(request_times: deque[float]) -> bool:
    now = monotonic()
    window_start = now - 60
    while request_times and request_times[0] < window_start:
        request_times.popleft()
    if len(request_times) >= MAX_WEBSOCKET_MESSAGES_PER_MINUTE:
        return False
    request_times.append(now)
    return True
