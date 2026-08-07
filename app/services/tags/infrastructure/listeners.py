from app.core.event_bus import Event, EventBus
from app.core.logging import logger
from app.services.tags.domain.events import TAG_EVENT_TYPES


async def log_event(event: Event) -> None:
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        task_id=str(task_id) if (task_id := getattr(event, "task_id", None)) else None,
    )


def register_listeners(bus: EventBus) -> None:
    for event_type in TAG_EVENT_TYPES:
        bus.subscribe(event_type, log_event)
