"""In-process pub/sub event bus.

Listeners are scheduled via FastAPI :class:`BackgroundTasks`, which run *after*
the HTTP response has been returned (FRD §5). This guarantees domain events
never extend request latency. Phase 1 deliberately omits retry, dead-letter,
and circuit-breaker support — see TIS §7.2 for the rationale.
"""

from __future__ import annotations

import collections
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

type EventHandler = Callable[[Any], Any]


class Event(BaseModel):
    """Base class for every domain event."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Subscribe handlers to event types; publish via BackgroundTasks."""

    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[EventHandler]] = collections.defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        """Register ``handler`` for ``event_type``. Handlers fire in subscription order."""
        self._listeners[event_type].append(handler)

    async def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        """Schedule every handler for ``type(event)`` to run after the response.

        Handlers run sequentially in registration order via FastAPI's
        background-tasks queue; an exception in one handler does not stop the
        rest (FastAPI logs the traceback).
        """
        for handler in self._listeners[type(event)]:
            background_tasks.add_task(handler, event)
