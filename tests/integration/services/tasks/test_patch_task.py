from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_patch_partial_update_returns_200(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x", priority=2)
    r = await client.patch(f"/v1/tasks/{task_id}", json={"priority": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == 5
    assert body["title"] == "x"  # untouched


@pytest.mark.asyncio
async def test_patch_status_transition_reflected_in_body(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "completed"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_patch_empty_body_returns_422_empty_update(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "empty_update"


@pytest.mark.asyncio
async def test_patch_rejects_server_owned_id(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={"id": 999})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "read_only_field"
    assert err["details"] == {"field": "id"}


@pytest.mark.asyncio
async def test_patch_rejects_server_owned_created_at(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(
        f"/v1/tasks/{task_id}",
        json={"created_at": "2026-01-01T00:00:00Z"},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "read_only_field"
    assert err["details"] == {"field": "created_at"}


@pytest.mark.asyncio
async def test_patch_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.patch("/v1/tasks/99999", json={"priority": 5})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "task_not_found"


@pytest.mark.asyncio
async def test_patch_no_op_returns_200(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("x", priority=2)
    # Supplies a field but does not change it — service-layer rule: no events,
    # but the endpoint still returns 200 with the current row.
    r = await client.patch(f"/v1/tasks/{task_id}", json={"priority": 2})
    assert r.status_code == 200
    assert r.json()["priority"] == 2
