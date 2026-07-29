from typing import Final

from app.core.event_bus import Event


class WorkflowUpdated(Event):
    version: int
    states: list[str]


# Listener registration enumerates these; keep in lock-step with WorkflowService.
WORKFLOW_EVENT_TYPES: Final[tuple[type[Event], ...]] = (WorkflowUpdated,)
