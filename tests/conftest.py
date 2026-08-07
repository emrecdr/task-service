# All tests run against a throwaway Postgres (testcontainers). Per-test isolation is
# TRUNCATE ... RESTART IDENTITY + reseed — fast, and avoids drop/create per test.

import os

# Lock APP_ENV before app modules import.
os.environ.setdefault("APP_ENV", "test")
# Keep the outbox relay off under test: a background poller would race per-test assertions
# on outbox contents. Tests drive delivery explicitly via ``deliver_pending``.
os.environ.setdefault("OUTBOX_RELAY_ENABLED", "false")

from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from typing import Any

import pytest
from app.core import database
from app.core.errors import ErrorCode
from app.main import app
from app.services.workflows.infrastructure.seed import seed_workflow_if_missing
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer

type CreateTask = Callable[..., Awaitable[str]]
type InstallWorkflow = Callable[[dict[str, Any]], Awaitable[None]]

# ``tags`` is listed explicitly: CASCADE reaches ``task_tags`` through its FK to ``tasks``, but
# the vocabulary itself has no FK to anything, so it would otherwise survive between tests and
# make tag assertions depend on execution order.
_TRUNCATE = text("TRUNCATE tasks, tags, workflow_definitions, outbox RESTART IDENTITY CASCADE")


@pytest.fixture(scope="session", autouse=True)
def postgres_url() -> Iterator[str]:
    """Start one Postgres for the whole session; point the app engine at it (NullPool).

    Yields the URL so a test needing a *second* database on the same server (the
    migration-drift gate) can derive one instead of starting another container.
    """
    with PostgresContainer("postgres:17", driver="asyncpg") as pg:
        url = pg.get_connection_url()
        # NullPool: each operation opens a fresh connection on the current loop — needed
        # because Schemathesis drives the ASGI app in a separate portal loop, and a shared
        # pool's connections are loop-bound ("attached to a different loop").
        database.configure(url, poolclass=NullPool)
        yield url


@pytest.fixture(scope="session", autouse=True)
async def _schema(postgres_url: str) -> None:  # pyright: ignore[reportUnusedFunction]
    """Build the schema once for the session.

    DDL lives in an *async* fixture rather than in ``postgres_url`` (which is sync) so it runs on
    the test event loop instead of creating engine state on a closed one —
    ``asyncio_default_fixture_loop_scope`` is ``session``, so that is the same loop every test
    sees. Session-scoped because nothing ever drops the schema: running ``create_all`` before each
    test re-paid a connection round trip several hundred times to confirm it had nothing to do.
    """
    await database.init_schema()


@pytest.fixture(autouse=True)
async def _fresh_data(_schema: None) -> None:  # pyright: ignore[reportUnusedFunction]
    """Reset rows between tests: TRUNCATE + reseed. Depends on ``_schema`` so the tables exist
    before the first TRUNCATE, rather than relying on fixture declaration order."""
    async with database.session_factory() as session:
        await session.execute(_TRUNCATE)
        await session.commit()
    await seed_workflow_if_missing()


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """A bare `AsyncSession` for tests that drive the repository / DB directly."""
    async with database.session_factory() as s:
        yield s


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


@pytest.fixture
def install_workflow(client: AsyncClient) -> InstallWorkflow:
    """Factory: ``await install_workflow(document)`` makes that definition the active one.

    Every workflow-governed test starts by replacing the seeded any→any definition, so the
    PUT-and-assert-200 lives here rather than once per test module.
    """

    async def _factory(document: dict[str, Any]) -> None:
        r = await client.put("/v1/workflow", json=document)
        assert r.status_code == 200, r.text

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
