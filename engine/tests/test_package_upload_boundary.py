from collections.abc import AsyncGenerator
from io import BytesIO
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, cast

import pytest
import starlette.formparsers as formparsers
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData, UploadFile
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import Message, Receive, Scope, Send

import engine.api.routes.packages as package_routes
from engine.api.errors import ErrorEnvelope
from engine.api.main import create_app
from engine.api.middleware.auth import CurrentUser, get_current_user
from engine.api.middleware.body_limit import RequestBodyLimitMiddleware
from engine.db.session import get_db_session
from engine.tests.package_loader_fixtures import package_archive


async def _unbound_db_session() -> AsyncGenerator[AsyncSession]:
    async with AsyncSession() as session:
        yield session


async def _admin_user() -> CurrentUser:
    return CurrentUser(
        subject="00000000-0000-0000-0000-000000000001",
        role="authenticated",
        app_role="admin",
    )


def _admin_app_without_database() -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_db_session] = _unbound_db_session
    app.dependency_overrides[get_current_user] = _admin_user
    return app


def test_package_import_rejects_upload_larger_than_memory_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：HTTP 剧本包限制小于提交的请求体。
    monkeypatch.setattr(package_routes, "MAX_PACKAGE_UPLOAD_BYTES", 8, raising=False)
    client = TestClient(_admin_app_without_database())

    # 当：管理员上传的字节数超出限制。
    response = client.post(
        "/api/v1/packages",
        files={"file": ("large.zip", b"123456789", "application/zip")},
    )
    detail = ErrorEnvelope.model_validate_json(response.content).error

    # 则：在解析归档或访问数据库前拒绝请求体。
    assert response.status_code == 400
    assert detail.code == "PACKAGE_UPLOAD_TOO_LARGE"


def test_package_import_authenticates_before_parsing_multipart(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：如果未经认证的请求到达 multipart 解析步骤，该解析将会失败。
    parsed = False

    async def fail_if_parsed(*_args: object, **_kwargs: object) -> object:
        nonlocal parsed
        parsed = True
        raise AssertionError("multipart body was parsed before authentication")

    monkeypatch.setattr(Request, "form", fail_if_parsed)
    client = TestClient(create_app())

    body_read = False

    def unauthorized_body():
        nonlocal body_read
        body_read = True
        yield b"body-must-not-be-read"

    # 当：没有 Bearer Token 的调用方提交剧本包请求体。
    response = client.post(
        "/api/v1/packages",
        content=unauthorized_body(),
        headers={"content-type": "multipart/form-data; boundary=unused"},
    )

    # 则：管理员依赖项在不读取 multipart 数据的情况下拒绝请求。
    assert response.status_code == 401
    assert ErrorEnvelope.model_validate_json(response.content).error.code == "AUTH_REQUIRED"
    assert parsed is False
    assert body_read is False


def test_package_import_closes_upload_files_from_invalid_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：multipart 解析生成了上传文件，但字段名不符合唯一 file 契约。
    upload = UploadFile(BytesIO(), filename="wrong.zip")

    async def invalid_form(*_args: object, **_kwargs: object) -> FormData:
        return FormData([("wrong", upload)])

    monkeypatch.setattr(Request, "form", invalid_form)
    client = TestClient(_admin_app_without_database())

    # 当：管理员提交无效表单。
    response = client.post(
        "/api/v1/packages",
        content=b"unused",
        headers={"content-type": "multipart/form-data; boundary=unused"},
    )

    # 则：返回稳定错误，并关闭解析器创建的临时文件句柄。
    assert response.status_code == 400
    detail = ErrorEnvelope.model_validate_json(response.content).error
    assert detail.code == "PACKAGE_UPLOAD_INVALID"
    assert upload.file.closed is True


def test_request_body_limit_counts_streamed_chunks_without_content_length() -> None:
    # 给定：较小的 ASGI 请求体预算，以及一个消费请求流的端点。
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        default_limit_bytes=8,
        package_limit_bytes=8,
    )

    async def consume(request: Request) -> dict[str, int]:
        content = await request.body()
        return {"size": len(content)}

    app.add_api_route("/consume", consume, methods=["POST"])
    client = TestClient(app)

    # 当：生成器在没有 Content-Length 时发送超过累计限制的数据。
    response = client.post(
        "/consume",
        content=(chunk for chunk in (b"1234", b"5678", b"9")),
        headers={"content-type": "application/octet-stream"},
    )

    # 则：接收包装器使用共享错误信封拒绝请求。
    assert response.status_code == 413
    assert (
        ErrorEnvelope.model_validate_json(response.content).error.code == "REQUEST_BODY_TOO_LARGE"
    )


def test_request_body_limit_replays_accepted_stream_to_endpoint() -> None:
    # 给定：合法分块请求体恰好达到累计字节预算。
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        default_limit_bytes=8,
        package_limit_bytes=8,
    )

    async def read_body(request: Request) -> dict[str, str]:
        return {"body": (await request.body()).decode("ascii")}

    app.add_api_route("/read", read_body, methods=["POST"])
    client = TestClient(app)

    # 当：中间件预读取后把内容回放给端点。
    response = client.post(
        "/read",
        content=(chunk for chunk in (b"1234", b"5678")),
        headers={"content-type": "application/octet-stream"},
    )

    # 则：端点读取到完整且顺序不变的请求体。
    assert response.status_code == 200
    assert response.json() == {"body": "12345678"}


def test_request_body_limit_rejects_oversized_body_when_endpoint_does_not_read_it() -> None:
    # 给定：一个不会读取请求体的端点和较小的累计字节预算。
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        default_limit_bytes=8,
        package_limit_bytes=8,
    )

    async def ignore_body() -> dict[str, bool]:
        return {"accepted": True}

    app.add_api_route("/ignore", ignore_body, methods=["POST"])
    client = TestClient(app)

    # 当：无 Content-Length 的分块请求体超过预算。
    response = client.post(
        "/ignore",
        content=(chunk for chunk in (b"1234", b"5678", b"9")),
        headers={"content-type": "application/octet-stream"},
    )

    # 则：中间件在调用端点前完成累计检查并返回统一错误。
    assert response.status_code == 413
    assert (
        ErrorEnvelope.model_validate_json(response.content).error.code == "REQUEST_BODY_TOO_LARGE"
    )


def test_package_body_limit_counts_chunks_after_authentication_boundary() -> None:
    # 给定：剧本包路由采用延迟读取，但端点在鉴权通过后会消费上传体。
    app = FastAPI()
    app.add_middleware(
        RequestBodyLimitMiddleware,
        default_limit_bytes=8,
        package_limit_bytes=8,
    )

    async def consume_package(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    app.add_api_route("/api/v1/packages", consume_package, methods=["POST"])
    client = TestClient(app)

    # 当：无 Content-Length 的分块上传超过剧本包预算。
    response = client.post(
        "/api/v1/packages",
        content=(chunk for chunk in (b"1234", b"5678", b"9")),
        headers={"content-type": "application/octet-stream"},
    )

    # 则：延迟计数仍在端点处理上传前返回统一 413。
    assert response.status_code == 413
    assert (
        ErrorEnvelope.model_validate_json(response.content).error.code == "REQUEST_BODY_TOO_LARGE"
    )


async def test_package_body_limit_closes_multipart_file_created_before_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 给定：首个分块足以让 Starlette 创建上传文件，后续分块才突破累计预算。
    created_files: list[BinaryIO] = []

    def create_tracked_spooled_file(*, max_size: int = 0) -> BinaryIO:
        temporary_file = cast(BinaryIO, SpooledTemporaryFile(max_size=max_size, mode="w+b"))
        created_files.append(temporary_file)
        return temporary_file

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", create_tracked_spooled_file)
    boundary = "acceptance-boundary"
    first_chunk = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="large.zip"\r\n'
        "Content-Type: application/zip\r\n\r\n"
        "1234"
    ).encode("ascii")
    final_chunk = f"56789\r\n--{boundary}--\r\n".encode("ascii")

    async def parse_package_form(scope: Scope, receive: Receive, send: Send) -> None:
        request = Request(scope, receive)
        form = await request.form()
        await form.close()
        await JSONResponse({"accepted": True})(scope, receive, send)

    middleware = RequestBodyLimitMiddleware(
        parse_package_form,
        default_limit_bytes=len(first_chunk),
        package_limit_bytes=len(first_chunk),
    )
    incoming_messages = iter(
        (
            {"type": "http.request", "body": first_chunk, "more_body": True},
            {"type": "http.request", "body": final_chunk, "more_body": False},
        )
    )
    sent_messages: list[Message] = []

    async def receive() -> Message:
        return cast(Message, next(incoming_messages))

    async def send(message: Message) -> None:
        sent_messages.append(message)

    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/packages",
            "raw_path": b"/api/v1/packages",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode())],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        },
    )

    # 当：multipart parser 已持有文件句柄后，累计限制在下一分块抛出 OSError。
    await middleware(scope, receive, send)

    # 则：Starlette 在中间件转换 413 前关闭所有已创建的临时文件。
    response_start = next(
        message for message in sent_messages if message["type"] == "http.response.start"
    )
    response_body = next(
        message for message in sent_messages if message["type"] == "http.response.body"
    )
    assert response_start["status"] == 413
    assert ErrorEnvelope.model_validate_json(response_body["body"]).error.code == (
        "REQUEST_BODY_TOO_LARGE"
    )
    assert len(created_files) == 1
    assert all(temporary_file.closed for temporary_file in created_files)


def test_package_import_returns_400_for_invalid_yaml_encoding() -> None:
    # 给定：管理员上传一个清单不是 UTF-8 编码的 ZIP。
    client = TestClient(_admin_app_without_database())
    archive = package_archive({"package.yml": b"\xff"})

    # 当：归档经过真实 HTTP 和导入服务边界。
    response = client.post(
        "/api/v1/packages",
        files={"file": ("invalid.zip", archive, "application/zip")},
    )
    detail = ErrorEnvelope.model_validate_json(response.content).error

    # 则：类型化剧本包错误被转换为客户端错误，而不是 500。
    assert response.status_code == 400
    assert detail.code == "PACKAGE_YAML_ENCODING_INVALID"
