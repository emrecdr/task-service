from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


async def test_delete_returns_204_then_get_404(client: AsyncClient) -> None:
    created = await client.post("/v1/tasks", json={"title": "to-delete", "priority": 1})
    assert created.status_code == 201
    task_id = created.json()["id"]

    deleted = await client.delete(f"/v1/tasks/{task_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    follow_up = await client.get(f"/v1/tasks/{task_id}")
    assert_error(follow_up, 404, ErrorCode.TASK_NOT_FOUND, details={"id": task_id})


async def test_delete_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.delete("/v1/tasks/99999")
    assert_error(r, 404, ErrorCode.TASK_NOT_FOUND)
