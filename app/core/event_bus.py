"""In-process pub/sub event bus; listeners run via FastAPI ``BackgroundTasks`` after the response."""

import collections
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field

type EventHandler = Callable[[Any], Any]


class Event(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[EventHandler]] = collections.defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: EventHandler) -> None:
        # Handlers fire in subscription order.
        self._listeners[event_type].append(handler)

    def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        for handler in self._listeners[type(event)]:
            background_tasks.add_task(handler, event)
