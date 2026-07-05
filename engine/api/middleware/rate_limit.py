from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import override

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from engine.api.errors import ErrorDetail, ErrorEnvelope

# ── API 网关限流中间件 ──


class RateLimitMiddleware(BaseHTTPMiddleware):
    _limit_per_minute: int

    def __init__(self, app: ASGIApp, limit_per_minute: int) -> None:
        super().__init__(app)
        self._limit_per_minute = limit_per_minute
        self._requests: defaultdict[str, deque[float]] = defaultdict(deque)

    # 每个客户端保留 60 秒滑动窗口内的请求时间
    @override
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        client_host = request.client.host if request.client else "unknown"
        window_start = monotonic() - 60
        request_times = self._requests[client_host]

        while request_times and request_times[0] < window_start:
            _ = request_times.popleft()

        if len(request_times) >= self._limit_per_minute:
            envelope = ErrorEnvelope(
                error=ErrorDetail(
                    code="RATE_LIMITED",
                    message="请求过于频繁",
                ),
            )
            return JSONResponse(
                status_code=429,
                content=envelope.model_dump(mode="json"),
            )

        request_times.append(monotonic())
        return await call_next(request)
