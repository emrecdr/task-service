import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_delete_returns_204_then_get_404(client: AsyncClient) -> None:
    created = await client.post("/v1/tasks", json={"title": "to-delete", "priority": 1})
    assert created.status_code == 201
    task_id = created.json()["id"]

    deleted = await client.delete(f"/v1/tasks/{task_id}")
    assert deleted.status_code == 204
    assert deleted.content == b""

    follow_up = await client.get(f"/v1/tasks/{task_id}")
    assert follow_up.status_code == 404
    err = follow_up.json()["error"]
    assert err["code"] == "task_not_found"
    assert err["details"] == {"id": task_id}


@pytest.mark.asyncio
async def test_delete_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.delete("/v1/tasks/99999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "task_not_found"
