from collections.abc import Awaitable, Callable

from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


async def test_patch_partial_update_returns_200(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x", priority=2)
    r = await client.patch(f"/v1/tasks/{task_id}", json={"priority": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["priority"] == 5
    assert body["title"] == "x"  # untouched


async def test_patch_status_transition_reflected_in_body(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "completed"})
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


async def test_patch_empty_body_returns_422_empty_update(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={})
    assert_error(r, 422, ErrorCode.EMPTY_UPDATE)


async def test_patch_schema_documents_min_properties(client: AsyncClient) -> None:
    r = await client.get("/openapi.json")
    assert r.status_code == 200
    task_patch_schema = r.json()["components"]["schemas"]["TaskPatch"]
    assert task_patch_schema.get("minProperties") == 1


async def test_patch_rejects_server_owned_id(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("x")
    r = await client.patch(f"/v1/tasks/{task_id}", json={"id": 999})
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "id"})


async def test_patch_rejects_server_owned_created_at(
    client: AsyncClient, create_task: Callable[..., Awaitable[int]]
) -> None:
    task_id = await create_task("x")
    r = await client.patch(
        f"/v1/tasks/{task_id}",
        json={"created_at": "2026-01-01T00:00:00Z"},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "created_at"})


async def test_patch_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.patch("/v1/tasks/99999", json={"priority": 5})
    assert_error(r, 404, ErrorCode.TASK_NOT_FOUND)


async def test_patch_no_op_returns_200(client: AsyncClient, create_task: Callable[..., Awaitable[int]]) -> None:
    task_id = await create_task("x", priority=2)
    r = await client.patch(f"/v1/tasks/{task_id}", json={"priority": 2})
    assert r.status_code == 200
    assert r.json()["priority"] == 2
