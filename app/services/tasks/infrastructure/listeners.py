"""Event listeners for the tasks feature."""

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
