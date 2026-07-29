import sys

import structlog

from app.core.config import settings


def setup_logging() -> None:
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.json_logs:
        # format_exc_info belongs to machine renderers only; ConsoleRenderer
        # pretty-prints exceptions itself and warns if the field is pre-formatted.
        processors.extend([structlog.processors.format_exc_info, structlog.processors.JSONRenderer()])
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(settings.log_level_int),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )


logger = structlog.get_logger("app")
