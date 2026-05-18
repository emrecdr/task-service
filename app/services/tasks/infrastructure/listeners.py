from app.core.event_bus import Event, EventBus
from app.core.logging import logger
from app.services.tasks.domain.events import TASK_EVENT_TYPES


async def log_event(event: Event) -> None:
    task = getattr(event, "task", None)
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        task_id=getattr(task, "id", None),
    )


def register_listeners(bus: EventBus) -> None:
    for event_type in TASK_EVENT_TYPES:
        bus.subscribe(event_type, log_event)
