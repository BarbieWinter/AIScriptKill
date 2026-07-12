"""为 T-2.6 之前的 API 提供受限的纯心跳 WebSocket 传输。"""

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import Mapping
from threading import Lock
from time import monotonic
from typing import Final, cast
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

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
async def websocket_endpoint(websocket: WebSocket, session_id: UUID) -> None:
    """在 T-2.6 前提供资源受限的心跳通道。

    Args:
        websocket: 通过路径和容量校验后接受的客户端连接。
        session_id: 处理器运行前由 FastAPI 解析的会话 UUID。

    Returns:
        无返回值。处理器只针对 `session.ping` 输入发送 `session.pong`。

    Notes:
        JWT 会话绑定和玩法事件流仍属于 T-2.6。本临时端点仍会限制并发连接、输入
        大小与速率以及空闲时长，避免未认证心跳无限占用资源。
    """
    client = websocket.client.host if websocket.client is not None else "unknown"
    if not _CONNECTIONS.acquire(client):
        await websocket.close(code=1013, reason="WebSocket capacity exceeded")
        return

    try:
        request_times: deque[float] = deque()
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
                raw_event = cast(object, json.loads(raw_text))
            except json.JSONDecodeError:
                await websocket.close(code=1003, reason="WebSocket message must be JSON")
                return
            event_type: object | None = None
            if isinstance(raw_event, Mapping):
                event = cast(Mapping[str, object], raw_event)
                event_type = event.get("type")
            if event_type == "session.ping":
                await websocket.send_json(
                    {"type": "session.pong", "data": {"session_id": str(session_id)}},
                )
    except WebSocketDisconnect:
        return
    finally:
        _CONNECTIONS.release(client)


def _within_message_rate(request_times: deque[float]) -> bool:
    now = monotonic()
    window_start = now - 60
    while request_times and request_times[0] < window_start:
        request_times.popleft()
    if len(request_times) >= MAX_WEBSOCKET_MESSAGES_PER_MINUTE:
        return False
    request_times.append(now)
    return True
