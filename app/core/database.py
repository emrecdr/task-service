from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import Pool
from sqlmodel import SQLModel

from app.core.config import settings

# The async engine + sessionmaker are module state, but deliberately RE-BINDABLE:
# the test harness starts a throwaway Postgres container *after* import and points the
# app at it via ``configure()``. Call sites resolve the live sessionmaker through
# ``get_sessionmaker()`` / ``session_factory()`` rather than binding a name at import.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _pool_options(poolclass: type[Pool] | None) -> dict[str, Any]:
    """Engine pool kwargs. A test-supplied ``poolclass`` (e.g. ``NullPool``) takes no sizing
    args; otherwise size the async ``QueuePool`` from settings and keep ``pool_pre_ping``."""
    if poolclass is not None:
        return {"poolclass": poolclass}
    return {
        "pool_pre_ping": True,
        "pool_size": settings.db_pool_size,
        "max_overflow": settings.db_max_overflow,
        "pool_recycle": settings.db_pool_recycle_seconds,
    }


def configure(database_url: str | None = None, *, poolclass: type[Pool] | None = None) -> None:
    """(Re)bind the engine + sessionmaker to a database URL (defaults to settings).

    ``expire_on_commit=False`` is load-bearing: post-commit attribute reads
    (``Task.snapshot()`` for event payloads, ``record.version``) must not trigger a
    lazy refresh, which under ``AsyncSession`` would require an await in a sync context.

    ``poolclass`` lets the test harness pass ``NullPool`` so each operation opens a
    fresh connection on the current event loop (function-scoped async tests otherwise
    hit asyncpg's "attached to a different loop" errors on a shared pool).
    """
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url or settings.database_url, **_pool_options(poolclass))
    _sessionmaker = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


def get_engine() -> AsyncEngine:
    if _engine is None:
        configure()
    assert _engine is not None
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        configure()
    assert _sessionmaker is not None
    return _sessionmaker


async def init_schema() -> None:
    """Create all tables. **Tests only** — production schema is owned by Alembic."""
    async with get_engine().begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def dispose_engine() -> None:
    """Release the connection pool on shutdown (Postgres, unlike in-memory SQLite)."""
    if _engine is not None:
        await _engine.dispose()


async def probe_database(session: AsyncSession) -> Exception | None:
    """Fail-soft liveness probe: run ``SELECT 1``. Returns ``None`` on success, or the
    caught driver exception on failure. The single place the readiness query and its
    caught-exception set live — ``/readyz`` and ``/diagnose`` each format their own body.
    """
    try:
        await session.scalar(text("SELECT 1"))
        return None
    except (OperationalError, DatabaseError) as err:
        return err


@asynccontextmanager
async def session_factory() -> AsyncGenerator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session
