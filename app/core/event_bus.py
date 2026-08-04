"""In-process pub/sub registry. Events are delivered by the transactional-outbox relay.

Producers no longer touch this bus: a write stages its events into the ``outbox`` table in the
same transaction (see ``app.core.outbox``), and the relay reconstructs each event and calls
``dispatch`` here. So this class is just the subscription registry plus the awaited fan-out the
relay drives. Scope is a single worker — each worker registers its own listeners and delivers
its own claimed rows; that is correct for the log-only listeners, and any cross-worker consumer
would be a new outbox listener, not a change here.
"""

import collections
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid7

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    # uuid7 (time-ordered): the outbox persists this id in the row payload, and it is the key
    # listeners dedupe on across at-least-once re-delivery — a durable identifier, not a
    # transient one.
    id: UUID = Field(default_factory=uuid7)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


type EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[EventHandler]] = collections.defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        # Handlers fire in subscription order.
        self._listeners[event_type].append(handler)

    async def dispatch(self, event: Event) -> None:
        """Deliver an event to its subscribers, in order. Called by the outbox relay.

        Handlers are awaited sequentially; a raising handler propagates so the relay records
        the row as a failed delivery and retries it (at-least-once — handlers are idempotent).
        """
        # ``.get`` (not ``[]``) so dispatching an event with no subscribers doesn't
        # auto-vivify an empty list — keeps ``subscriptions()`` free of phantom rows.
        for handler in self._listeners.get(type(event), ()):
            await handler(event)

    def subscriptions(self) -> dict[str, int]:
        """Registered event types → handler count. Read-only view for diagnostics."""
        return {event_type.__name__: len(handlers) for event_type, handlers in self._listeners.items()}
