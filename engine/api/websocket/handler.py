from collections.abc import Mapping
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

# ── 会话实时通道 ──

router = APIRouter(tags=["websocket"])


# ── 心跳协议骨架 ──


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Accept a session WebSocket and handle heartbeat messages."""
    await websocket.accept()
    try:
        while True:
            raw_event = cast(object, await websocket.receive_json())
            event_type: object | None = None
            if isinstance(raw_event, Mapping):
                event = cast(Mapping[str, object], raw_event)
                event_type = event.get("type")
            if event_type == "session.ping":
                await websocket.send_json(
                    {"type": "session.pong", "data": {"session_id": session_id}},
                )
    except WebSocketDisconnect:
        return
