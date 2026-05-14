# NOTE: this suite is *not* compatible with pytest-xdist. The SQLite :memory:
# engine is bound via StaticPool to a single shared connection (TIS §6.1) —
# parallel workers would race against the same schema. Keep tests sequential.

import os

# Lock the env BEFORE app modules import. Settings is module-scoped (TIS §7.6).
os.environ.setdefault("APP_ENV", "test")

from collections.abc import AsyncIterator, Awaitable, Callable

import pytest
from app.core.database import engine, init_schema
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlmodel import SQLModel


@pytest.fixture(autouse=True)
def _fresh_schema() -> None:
    """Recreate the in-memory schema between tests so they are isolated."""
    SQLModel.metadata.drop_all(engine)
    init_schema()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # ASGITransport does NOT run lifespan automatically — without this wrapper
    # app.state.event_bus is unset and every request raises AttributeError.
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c


@pytest.fixture
def create_task(client: AsyncClient) -> Callable[..., Awaitable[int]]:
    """Factory: ``await create_task(title, priority=3)`` → new task id."""

    async def _factory(title: str, priority: int = 3) -> int:
        r = await client.post("/v1/tasks", json={"title": title, "priority": priority})
        assert r.status_code == 201, r.text
        return int(r.json()["id"])

    return _factory
