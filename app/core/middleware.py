"""HTTP middlewares for cross-cutting request concerns."""

from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Generate/propagate ``X-Request-ID`` and bind it to the log context.

    A UUIDv4 is generated when the header is absent. The value is:

    1. attached to ``request.state.request_id`` so handlers (and the global
       exception handler) can read it,
    2. bound into ``structlog.contextvars`` so every log line for the request
       carries it,
    3. echoed back to the client on the response.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response: Response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = rid
        return response
