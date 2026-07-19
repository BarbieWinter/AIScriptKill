import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import ExitStack
from inspect import getdoc
from pathlib import Path
from types import FunctionType
from typing import cast
from uuid import UUID

import jwt
import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from jwt import PyJWKClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError

import engine.api.websocket.handler as websocket_handler
from engine.api.errors import ErrorEnvelope
from engine.api.main import create_app
from engine.api.middleware.auth import CurrentUser, SupabaseJwtVerifier, get_current_user
from engine.api.routes import actions, packages, sessions
from engine.db.session import get_db_session

ROUTERS = (sessions.router, actions.router, packages.router)


def _public_route_functions() -> tuple[FunctionType, ...]:
    route_functions: list[FunctionType] = []
    for router in ROUTERS:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            endpoint = route.endpoint
            if isinstance(endpoint, FunctionType) and not endpoint.__name__.startswith("_"):
                route_functions.append(endpoint)
    return tuple(route_functions)


PUBLIC_ROUTE_FUNCTIONS = _public_route_functions()


def _route_id(route_function: FunctionType) -> str:
    return route_function.__name__


async def _unbound_db_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession() as session:
        yield session


def _app_without_database() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db_session] = _unbound_db_session
    return app


async def _admin_user() -> CurrentUser:
    return CurrentUser(
        subject="00000000-0000-0000-0000-000000000001",
        role="authenticated",
        app_role="admin",
    )


@pytest.mark.parametrize(
    "route_function",
    PUBLIC_ROUTE_FUNCTIONS,
    ids=_route_id,
)
def test_public_route_docstring_describes_api_contract(
    route_function: FunctionType,
) -> None:
    # 给定：一个公开的 REST 路由函数。
    docstring = getdoc(route_function) or ""

    # 当：检查其面向开发者的 API 契约。
    required_sections = ("Args:", "Returns:", "Raises:", "ApiError")

    # 则：行为输入、输出和 API 错误条件均有记录。
    assert all(section in docstring for section in required_sections), docstring


def test_get_session_rejects_invalid_uuid_without_database() -> None:
    # 给定：API 使用无法访问真实数据库的未绑定会话。
    client = TestClient(_app_without_database())

    # 当：会话端点收到格式错误的 UUID 路径值。
    response = client.get("/api/v1/sessions/not-a-uuid")
    detail = ErrorEnvelope.model_validate_json(response.content).error

    # 则：路由返回文档中约定的稳定 API 错误。
    assert response.status_code == 400
    assert detail.code == "INVALID_SESSION_ID"


def test_admin_package_import_rejects_empty_upload_without_database() -> None:
    # 给定：API 使用未绑定会话，并收到空的剧本包文件。
    app = _app_without_database()
    app.dependency_overrides[get_current_user] = _admin_user
    client = TestClient(app)

    # 当：管理员提交空归档。
    response = client.post(
        "/api/v1/packages",
        files={"file": ("empty.zip", b"", "application/zip")},
    )
    detail = ErrorEnvelope.model_validate_json(response.content).error

    # 则：路由返回文档中约定的空上传错误。
    assert response.status_code == 400
    assert detail.code == "EMPTY_PACKAGE_UPLOAD"


def test_websocket_rejects_malformed_session_id_before_heartbeat() -> None:
    # 给定：会话路径值不是 UUID 的 WebSocket URL。
    client = TestClient(create_app())

    # 当：客户端尝试连接并发送心跳。
    with pytest.raises(WebSocketDisconnect) as disconnect_info:
        with client.websocket_connect("/api/v1/ws/not-a-uuid") as websocket:
            websocket.send_json({"type": "session.ping"})
            websocket.receive_json()

    # 则：FastAPI 在处理器接受套接字前拒绝该路径值。
    assert disconnect_info.value.code == 1008


def test_websocket_returns_valid_uuid_as_string_in_heartbeat() -> None:
    # 给定：包含有效会话 UUID 的 WebSocket URL。
    client = TestClient(create_app())
    session_id = UUID("12345678-1234-5678-1234-567812345678")

    # 当：客户端发送当前支持的心跳事件。
    with client.websocket_connect(f"/api/v1/ws/{session_id}") as websocket:
        websocket.send_json({"type": "session.ping"})
        # 则：服务器使用稳定的心跳信封和字符串 ID 响应。
        assert websocket.receive_json() == {
            "type": "session.pong",
            "data": {"session_id": str(session_id)},
        }


def test_websocket_rejects_binary_messages_with_supported_data_close_code() -> None:
    # 给定：心跳传输收到二进制帧，而不是 JSON 文本。
    client = TestClient(create_app())
    session_id = UUID("12345678-1234-5678-1234-567812345678")

    # 当：客户端提交不受支持的帧类型。
    with client.websocket_connect(f"/api/v1/ws/{session_id}") as websocket:
        websocket.send_bytes(b'{"type":"session.ping"}')
        with pytest.raises(WebSocketDisconnect) as disconnect_info:
            websocket.receive_json()

    # 则：处理器主动关闭连接，而不是泄露内部 KeyError。
    assert disconnect_info.value.code == 1003


def test_backend_launch_surfaces_bound_websocket_frames_before_asgi_buffering() -> None:
    # 给定：每个受支持的后端启动入口都有自己的 Uvicorn 参数。
    repository_root = Path(__file__).resolve().parents[2]
    makefile = (repository_root / "Makefile").read_text(encoding="utf-8")
    compose = (repository_root / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (repository_root / "engine" / "Dockerfile").read_text(encoding="utf-8")
    limits = "--ws-max-size 65536 --ws-max-queue 4"

    # 当/则：每条启动命令都在 ASGI 收到帧前应用传输限制。
    assert makefile.count(limits) == 4
    assert limits in compose
    assert '"--ws-max-size", "65536", "--ws-max-queue", "4"' in dockerfile


@pytest.mark.asyncio
async def test_uvicorn_transport_rejects_oversized_websocket_frame() -> None:
    # 给定：真实 Uvicorn 传输使用与部署环境相同的帧和队列限制。
    server_socket = socket.socket()
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", 0))
    server_socket.listen()
    port = cast(tuple[str, int], server_socket.getsockname())[1]
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(),
            log_level="critical",
            lifespan="off",
            ws_max_size=websocket_handler.MAX_WEBSOCKET_MESSAGE_BYTES,
            ws_max_queue=4,
        ),
    )
    server_task = asyncio.create_task(server.serve(sockets=[server_socket]))

    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started

        # 当：对端发送一个超出传输预算的文本帧。
        async with connect(
            f"ws://127.0.0.1:{port}/api/v1/ws/12345678-1234-5678-1234-567812345678",
            max_size=None,
            proxy=None,
        ) as websocket:
            await websocket.send("x" * (websocket_handler.MAX_WEBSOCKET_MESSAGE_BYTES + 1))
            with pytest.raises(ConnectionClosedError) as close_info:
                await websocket.recv()

        # 则：Uvicorn 在 ASGI 消息送达前于协议层关闭连接。
        assert close_info.value.rcvd is not None
        assert close_info.value.rcvd.code == 1009
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=5)
        server_socket.close()


def test_websocket_rejects_connections_beyond_per_client_capacity() -> None:
    # 给定：一个客户端已占用四个允许的心跳连接。
    client = TestClient(create_app())
    session_id = UUID("12345678-1234-5678-1234-567812345678")

    with ExitStack() as open_connections:
        for _ in range(websocket_handler.MAX_WEBSOCKET_CONNECTIONS_PER_CLIENT):
            open_connections.enter_context(client.websocket_connect(f"/api/v1/ws/{session_id}"))

        # 当：同一客户端尝试再建立一个连接。
        with pytest.raises(WebSocketDisconnect) as disconnect_info:
            with client.websocket_connect(f"/api/v1/ws/{session_id}"):
                pass

    # 则：使用临时过载关闭码拒绝超出容量的连接。
    assert disconnect_info.value.code == 1013


@pytest.mark.asyncio
async def test_websocket_releases_capacity_when_accept_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：服务器已预留容量，但 ASGI 握手在接受前失败。
    registry = _RecordingConnectionRegistry()
    monkeypatch.setattr(websocket_handler, "_CONNECTIONS", registry)
    failing_socket = cast(WebSocket, cast(object, _FailingAcceptWebSocket()))

    # 当：接受连接时在传输边界引发异常。
    with pytest.raises(RuntimeError, match="handshake failed"):
        await websocket_handler.websocket_endpoint(
            failing_socket,
            UUID("12345678-1234-5678-1234-567812345678"),
        )

    # 则：失败的预留容量恰好释放一次。
    assert registry.acquired == 1
    assert registry.released == 1


def test_websocket_closes_connection_after_message_rate_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：单个连接每分钟只能发送一条消息。
    monkeypatch.setattr(websocket_handler, "MAX_WEBSOCKET_MESSAGES_PER_MINUTE", 1)
    client = TestClient(create_app())
    session_id = UUID("12345678-1234-5678-1234-567812345678")

    # 当：第二次心跳超出单连接速率预算。
    with client.websocket_connect(f"/api/v1/ws/{session_id}") as websocket:
        websocket.send_json({"type": "session.ping"})
        assert websocket.receive_json()["type"] == "session.pong"
        websocket.send_json({"type": "session.ping"})
        with pytest.raises(WebSocketDisconnect) as disconnect_info:
            websocket.receive_json()

    # 则：临时传输使用策略违规代码关闭。
    assert disconnect_info.value.code == 1008


def test_supabase_jwt_verifier_requires_issuer_audience_and_expiry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：使用伪造签名密钥并捕获 PyJWT 调用的校验器。
    verifier = SupabaseJwtVerifier("https://project.supabase.co", "authenticated")
    monkeypatch.setattr(
        verifier,
        "_jwks_client",
        cast(PyJWKClient, cast(object, _FakeJwksClient())),
    )
    captured: dict[str, object] = {}

    def fake_decode(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "sub": "00000000-0000-0000-0000-000000000001",
            "exp": 4_102_444_800,
            "aud": "authenticated",
            "iss": "https://project.supabase.co/auth/v1",
        }

    monkeypatch.setattr(jwt, "decode", fake_decode)

    # 当：校验访问令牌。
    claims = verifier.verify("header.payload.signature")

    # 则：PyJWT 收到完整的 Supabase 令牌范围契约。
    assert claims.sub == "00000000-0000-0000-0000-000000000001"
    assert captured["audience"] == "authenticated"
    assert captured["issuer"] == "https://project.supabase.co/auth/v1"
    assert captured["options"] == {"require": ["aud", "exp", "iss", "sub"]}


class _FakeSigningKey:
    key = "test-key"


class _FakeJwksClient:
    def get_signing_key_from_jwt(self, _token: str) -> _FakeSigningKey:
        return _FakeSigningKey()


class _RecordingConnectionRegistry:
    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0

    def acquire(self, _client: str) -> bool:
        self.acquired += 1
        return True

    def release(self, _client: str) -> None:
        self.released += 1


class _FailingClientAddress:
    host = "failed-client"


class _FailingAcceptWebSocket:
    client = _FailingClientAddress()

    async def accept(self) -> None:
        raise RuntimeError("handshake failed")
