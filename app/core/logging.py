"""Structured logging via ``structlog`` plus the request-ID middleware.

The two concerns live together because the middleware exists solely to bind a
request-scoped UUID into ``structlog``'s context — every log line emitted
during the request then carries ``request_id`` automatically (FRD §7, TIS §7.3
and §7.4).
"""

from __future__ import annotations

import sys
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


def setup_logging() -> None:
    """Configure ``structlog`` for the current environment.

    - ``json_logs=True`` (``qa``, ``prod``) → single-line JSON output.
    - Otherwise → coloured human-readable output via ``ConsoleRenderer``.

    Called once from the FastAPI lifespan startup (TIS §7.7).
    """
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(settings.log_level_int),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("app")


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
