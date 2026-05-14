import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_round_trip_returns_200(client: AsyncClient) -> None:
    created = await client.post("/v1/tasks", json={"title": "alpha", "priority": 2})
    assert created.status_code == 201
    task_id = created.json()["id"]

    r = await client.get(f"/v1/tasks/{task_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task_id
    assert body["title"] == "alpha"
    assert body["priority"] == 2


@pytest.mark.asyncio
async def test_get_unknown_id_returns_404_envelope(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/99999")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "task_not_found"
    assert err["details"] == {"id": 99999}
    assert "message" in err
    assert "request_id" in err


@pytest.mark.asyncio
async def test_get_non_integer_id_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/not-an-int")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
