"""Event listeners for the tasks feature.

Phase 1 ships a single listener: :func:`log_event` writes one structured log
line per domain event so operators can trace task lifecycle changes through
the standard log pipeline (FRD §5.2).
"""

from app.core.event_bus import Event
from app.core.logging import logger


async def log_event(event: Event) -> None:
    task = getattr(event, "task", None)
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        task_id=getattr(task, "id", None),
    )
