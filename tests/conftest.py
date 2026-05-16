# StaticPool shares one connection process-wide; tests cannot run with pytest-xdist.

import os

# Lock APP_ENV before app modules import.
os.environ.setdefault("APP_ENV", "test")

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest
from app.core.database import engine, init_schema
from app.core.errors import ErrorCode
from app.main import app
from httpx import ASGITransport, AsyncClient, Response
from sqlmodel import SQLModel


@pytest.fixture(autouse=True)
def _fresh_schema() -> None:
    """Recreate the in-memory schema between tests so they are isolated."""
    SQLModel.metadata.drop_all(engine)
    init_schema()


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # ASGITransport does not run lifespan; wrap it explicitly.
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
