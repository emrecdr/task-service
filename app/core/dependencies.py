"""Cross-cutting FastAPI dependency providers (TIS §8).

Feature-specific providers live in the feature's own ``dependencies.py`` —
this module is only for primitives every feature might need.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlmodel import Session

from app.core.database import session_factory
from app.core.event_bus import EventBus


def get_session() -> Generator[Session]:
    """Yield a SQLModel session for the request lifetime."""
    with session_factory() as session:
        yield session


def get_event_bus(request: Request) -> EventBus:
    """Return the process-singleton event bus stored on ``app.state``.

    The bus is constructed once in the FastAPI lifespan startup (TIS §7.7).
    """
    bus = getattr(request.app.state, "event_bus", None)
    if not isinstance(bus, EventBus):
        # This should be impossible in production — the lifespan always runs.
        # Surfacing it as a clear error beats a confusing ``AttributeError``.
        raise RuntimeError("Event bus is not initialised; lifespan did not run.")
    return bus
