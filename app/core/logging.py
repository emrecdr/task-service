"""Structured logging via ``structlog`` (FRD §7, TIS §7.3)."""

from __future__ import annotations

import sys

import structlog

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
