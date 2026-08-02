"""In-process pub/sub event bus; listeners run via FastAPI ``BackgroundTasks`` after the response.

Scope is a single worker: events reach only handlers registered in *this* process, so with
``WEB_CONCURRENCY>1`` a worker sees only its own events. Correct for the current log-only
listeners (each worker logs its own events); a cross-worker or durable listener (notifications,
outbox, read-model) would need a transactional outbox or Postgres ``LISTEN/NOTIFY``. Deferred
until such a listener is scheduled — see TIS §8.2 (Worker scope).
"""

import collections
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


type EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[EventHandler]] = collections.defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        # Handlers fire in subscription order.
        self._listeners[event_type].append(handler)

    def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        # ``.get`` (not ``[]``) so publishing an event with no subscribers doesn't
        # auto-vivify an empty list — keeps ``subscriptions()`` free of phantom rows.
        for handler in self._listeners.get(type(event), ()):
            background_tasks.add_task(handler, event)

    def subscriptions(self) -> dict[str, int]:
        """Registered event types → handler count. Read-only view for diagnostics."""
        return {event_type.__name__: len(handlers) for event_type, handlers in self._listeners.items()}
