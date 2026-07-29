from app.core.event_bus import Event, EventBus
from app.core.logging import logger
from app.services.workflows.domain.events import WORKFLOW_EVENT_TYPES


async def log_event(event: Event) -> None:
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        version=getattr(event, "version", None),
    )


def register_listeners(bus: EventBus) -> None:
    for event_type in WORKFLOW_EVENT_TYPES:
        bus.subscribe(event_type, log_event)
