from collections.abc import Awaitable, Callable

import pytest
from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


@pytest.mark.asyncio
async def test_put_full_replace_returns_200(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("original")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"title": "replaced", "description": "d", "status": "in_progress", "priority": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task_id
    assert body["title"] == "replaced"
    assert body["description"] == "d"
    assert body["status"] == "in_progress"
    assert body["priority"] == 5


@pytest.mark.asyncio
async def test_put_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.put(
        "/v1/tasks/99999",
        json={"title": "x", "priority": 1},
    )
    assert_error(r, 404, ErrorCode.TASK_NOT_FOUND)


@pytest.mark.asyncio
async def test_put_title_collision_returns_409(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    await create_task("first")
    second = await create_task("second")
    r = await client.put(
        f"/v1/tasks/{second}",
        json={"title": "  FIRST  ", "priority": 1},
    )
    assert_error(r, 409, ErrorCode.DUPLICATE_TASK)


@pytest.mark.asyncio
async def test_put_missing_required_field_returns_422(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.put(f"/v1/tasks/{task_id}", json={"title": "y"})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_put_rejects_server_owned_id(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("x")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"id": 1, "title": "y", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "id"})


@pytest.mark.asyncio
async def test_put_rejects_server_owned_created_at(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"created_at": "2026-01-01T00:00:00Z", "title": "y", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "created_at"})
