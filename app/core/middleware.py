import time
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import logger


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
