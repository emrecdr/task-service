"""Event listeners for the tasks feature.

Phase 1 ships a single listener: :func:`log_event` writes one structured log
line per domain event so operators can trace task lifecycle changes through
the standard log pipeline (FRD §5.2). :func:`register_listeners` wires it
to the shared :class:`EventBus` — kept inside the feature so adding a 6th
event type doesn't force an edit to ``app.main``.
"""

from app.core.event_bus import Event, EventBus
from app.core.logging import logger
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)

_TASK_EVENT_TYPES: tuple[type[Event], ...] = (
    TaskCreated,
    TaskUpdated,
    TaskStatusChanged,
    TaskCompleted,
    TaskDeleted,
)


async def log_event(event: Event) -> None:
    task = getattr(event, "task", None)
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        task_id=getattr(task, "id", None),
    )


def register_listeners(bus: EventBus) -> None:
    """Subscribe the feature's listeners to every domain event it emits."""
    for event_type in _TASK_EVENT_TYPES:
        bus.subscribe(event_type, log_event)
