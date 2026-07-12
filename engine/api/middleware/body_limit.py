"""在框架解析前应用 ASGI 请求体大小限制。"""

from http import HTTPStatus
from tempfile import SpooledTemporaryFile
from typing import IO, Final, cast, final

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from engine.api.errors import ErrorDetail, ErrorEnvelope
from engine.core.package_archive import MAX_PACKAGE_UPLOAD_BYTES

DEFAULT_REQUEST_BODY_BYTES: Final = 1024 * 1024
PACKAGE_MULTIPART_OVERHEAD_BYTES: Final = 1024 * 1024
REQUEST_BODY_SPOOL_BYTES: Final = 1024 * 1024
REQUEST_BODY_REPLAY_CHUNK_BYTES: Final = 1024 * 1024


class RequestBodyTooLargeError(OSError):
    """表示累计 ASGI 请求体字节数超过路由预算。

    继承 ``OSError`` 是 multipart 资源边界的一部分：Starlette 解析器会在该异常
    离开请求流时关闭已经创建的临时上传文件，随后由本中间件统一转换为 413。
    """


@final
class RequestBodyLimitMiddleware:
    """在解析前拒绝超大 HTTP 请求体，包括分块请求。

    Args:
        app: 下游 ASGI 应用。
        default_limit_bytes: 普通 HTTP 请求体的最大字节数。
        package_limit_bytes: 剧本包导入 multipart 信封的字节预算。
    """

    def __init__(
        self,
        app: ASGIApp,
        default_limit_bytes: int = DEFAULT_REQUEST_BODY_BYTES,
        package_limit_bytes: int = MAX_PACKAGE_UPLOAD_BYTES + PACKAGE_MULTIPART_OVERHEAD_BYTES,
    ) -> None:
        self._app = app
        self._default_limit_bytes = default_limit_bytes
        self._package_limit_bytes = package_limit_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """应用选定的字节预算，并转发通过限制的 ASGI 请求。"""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        limit = self._limit_for(scope)
        if self._declared_length(scope) > limit:
            await self._send_rejection(scope, receive, send)
            return
        if self._defer_read_until_endpoint(scope):
            await self._call_with_deferred_limit(scope, receive, send, limit)
            return

        with SpooledTemporaryFile(max_size=REQUEST_BODY_SPOOL_BYTES, mode="w+b") as body:
            try:
                body_size, disconnected = await self._read_body(receive, body, limit)
            except RequestBodyTooLargeError:
                await self._send_rejection(scope, receive, send)
                return

            body.seek(0)
            replayed = 0

            async def replay_receive() -> Message:
                nonlocal replayed
                if disconnected:
                    return {"type": "http.disconnect"}
                if replayed >= body_size:
                    return {"type": "http.request", "body": b"", "more_body": False}
                chunk = body.read(REQUEST_BODY_REPLAY_CHUNK_BYTES)
                replayed += len(chunk)
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": replayed < body_size,
                }

            await self._app(scope, replay_receive, send)

    async def _call_with_deferred_limit(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        limit: int,
    ) -> None:
        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes):
                    consumed += len(chunk)
                    if consumed > limit:
                        raise RequestBodyTooLargeError
            return message

        try:
            await self._app(scope, limited_receive, send)
        except RequestBodyTooLargeError:
            await self._send_rejection(scope, receive, send)

    @staticmethod
    async def _read_body(receive: Receive, body: IO[bytes], limit: int) -> tuple[int, bool]:
        consumed = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return consumed, True
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            if isinstance(chunk, bytes):
                consumed += len(chunk)
                if consumed > limit:
                    raise RequestBodyTooLargeError
                _ = body.write(chunk)
            if not message.get("more_body", False):
                return consumed, False

    def _limit_for(self, scope: Scope) -> int:
        if scope.get("method") == "POST" and scope.get("path") == "/api/v1/packages":
            return self._package_limit_bytes
        return self._default_limit_bytes

    @staticmethod
    def _defer_read_until_endpoint(scope: Scope) -> bool:
        # 管理员依赖必须能在读取大型 multipart 前拒绝请求；认证通过后端点一定会消费上传体。
        return scope.get("method") == "POST" and scope.get("path") == "/api/v1/packages"

    @staticmethod
    def _declared_length(scope: Scope) -> int:
        raw_headers = scope.get("headers")
        if not isinstance(raw_headers, list):
            return 0
        headers = cast(list[tuple[bytes, bytes]], raw_headers)
        raw_length = next((value for name, value in headers if name == b"content-length"), b"0")
        try:
            return max(int(raw_length), 0)
        except ValueError:
            return 0

    @staticmethod
    async def _send_rejection(scope: Scope, receive: Receive, send: Send) -> None:
        envelope = ErrorEnvelope(
            error=ErrorDetail(
                code="REQUEST_BODY_TOO_LARGE",
                message="请求体超过服务器允许的大小",
            ),
        )
        response = JSONResponse(
            status_code=HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
            content=envelope.model_dump(mode="json"),
        )
        await response(scope, receive, send)
