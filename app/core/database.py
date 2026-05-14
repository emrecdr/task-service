"""SQLModel engine + session factory.

For SQLite ``:memory:`` we use ``poolclass=StaticPool`` and
``check_same_thread=False`` so every session in the process shares one
in-memory database. Without ``StaticPool`` SQLAlchemy hands each new
connection its own private ``:memory:`` DB — the test client, FastAPI app,
and readiness probe would all see different empty databases.

This is a Phase 1 quirk of the storage choice; it disappears the day
Postgres replaces SQLite. See TIS §6.1 for the full rationale.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings


def _engine_kwargs() -> dict[str, object]:
    """Dialect-aware connection arguments.

    SQLite needs StaticPool + ``check_same_thread=False``; other dialects use
    SQLAlchemy defaults.
    """
    if settings.database_url.startswith("sqlite"):
        return {
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    return {}


engine = create_engine(settings.database_url, **_engine_kwargs())


def init_schema() -> None:
    """Create all SQLModel-declared tables on the bound engine.

    Called once from the FastAPI lifespan startup (TIS §7.7) and from test
    fixtures that reset state between tests.
    """
    SQLModel.metadata.create_all(engine)


@contextmanager
def session_factory() -> Generator[Session, None, None]:
    """Yield a SQLModel ``Session`` bound to the module-level engine."""
    with Session(engine) as session:
        yield session
