import asyncio
import time
from typing import Final
from uuid import uuid4

import structlog
from fastapi import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.errors import ErrorCode, build_error_response
from app.core.logging import logger

# Applied to every response. Values are conservative defaults for an internal
# JSON API with no browser-rendered HTML: forbid MIME sniffing, framing, and
# referrer leakage. HSTS is added separately (prod-only — see below).
_SECURITY_HEADERS: Final[dict[str, str]] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# One year, include subdomains. Only meaningful over HTTPS, so gated to prod.
_HSTS_HEADER_NAME: Final[str] = "Strict-Transport-Security"
_HSTS_HEADER_VALUE: Final[str] = "max-age=31536000; includeSubDomains"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate/propagate ``X-Request-ID``, bind it to structlog, and emit one access log per request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
            response.headers["X-Request-ID"] = rid
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            return response
        finally:
            structlog.contextvars.clear_contextvars()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach standard hardening headers to every response; HSTS only in prod."""

    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        super().__init__(app)
        self._hsts_enabled = hsts_enabled

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        if self._hsts_enabled:
            response.headers[_HSTS_HEADER_NAME] = _HSTS_HEADER_VALUE
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared ``Content-Length`` exceeds ``max_bytes``.

    Guards the schema-less ``PUT /v1/workflow`` body (and every other write)
    against oversized payloads before the handler reads them. Streamed requests
    that omit ``Content-Length`` are not bounded here — a Phase-1 limitation.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None and content_length.isdigit() and int(content_length) > self._max_bytes:
            return build_error_response(
                request=request,
                code=ErrorCode.PAYLOAD_TOO_LARGE,
                message="Request body exceeds the maximum allowed size.",
                details={"max_bytes": self._max_bytes},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )
        return await call_next(request)


class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    """Bound handler wall-clock time; return 504 when the budget is exceeded."""

    def __init__(self, app: ASGIApp, *, timeout_seconds: float) -> None:
        super().__init__(app)
        self._timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await call_next(request)
        except TimeoutError:
            return build_error_response(
                request=request,
                code=ErrorCode.REQUEST_TIMEOUT,
                message="The server took too long to produce a response.",
                details={"timeout_seconds": self._timeout_seconds},
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            )
