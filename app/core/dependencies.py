from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import session_factory
from app.core.event_bus import EventBus


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with session_factory() as session:
        yield session


def get_event_bus(request: Request) -> EventBus:
    bus = getattr(request.app.state, "event_bus", None)
    if not isinstance(bus, EventBus):
        raise RuntimeError("Event bus is not initialised; lifespan did not run.")
    return bus


SessionDep = Annotated[AsyncSession, Depends(get_session)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
