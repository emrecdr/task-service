# All tests run against a throwaway Postgres (testcontainers). Per-test isolation is
# TRUNCATE ... RESTART IDENTITY + reseed — fast, and avoids drop/create per test.

import os

# Lock APP_ENV before app modules import.
os.environ.setdefault("APP_ENV", "test")

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

import pytest
from app.core import database
from app.core.errors import ErrorCode
from app.main import app
from app.services.workflows.infrastructure.seed import seed_workflow_if_missing
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

type CreateTask = Callable[..., Awaitable[str]]

_TRUNCATE = text("TRUNCATE tasks, workflow_definitions RESTART IDENTITY CASCADE")


@pytest.fixture(scope="session", autouse=True)
def _postgres_container() -> Iterator[None]:  # pyright: ignore[reportUnusedFunction]
    """Start one Postgres for the whole session; point the app engine at it (NullPool)."""
    with PostgresContainer("postgres:17", driver="asyncpg") as pg:
        # NullPool: each operation opens a fresh connection on the current loop — needed
        # because Schemathesis drives the ASGI app in a separate portal loop, and a shared
        # pool's connections are loop-bound ("attached to a different loop").
        database.configure(pg.get_connection_url(), poolclass=NullPool)
        yield


@pytest.fixture(autouse=True)
async def _fresh_data() -> None:  # pyright: ignore[reportUnusedFunction]
    """Ensure the schema exists (idempotent) then reset rows: TRUNCATE + reseed.

    Schema DDL runs here — in the test's own event loop / greenlet — rather than in
    the session fixture, which would create engine state on a closed loop.
    """
    await database.init_schema()
    async with database.session_factory() as session:
        await session.execute(_TRUNCATE)
        await session.commit()
    await seed_workflow_if_missing()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run lifespan; wrap it explicitly.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c


@pytest.fixture
def create_task(client: AsyncClient) -> CreateTask:
    """Factory: ``await create_task(title, priority=3)`` → new task id (UUID string)."""

    async def _factory(title: str, priority: int = 3) -> str:
        r = await client.post("/v1/tasks", json={"title": title, "priority": priority})
        assert r.status_code == 201, r.text
        return str(r.json()["id"])

    return _factory


def assert_error(
    response: Response,
    status_code: int,
    code: ErrorCode,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assert the standard error envelope; return the parsed ``error`` block."""
    assert response.status_code == status_code, response.text
    err: dict[str, Any] = response.json()["error"]
    assert err["code"] == code.value, f"expected code={code.value!r}, got {err['code']!r}"
    if details is not None:
        assert err["details"] == details
    assert "request_id" in err
    return err
