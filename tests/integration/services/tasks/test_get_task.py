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


# SQLite stores ids as signed 64-bit ints; values past 2**63 - 1 used to crash
# the driver with OverflowError → 500. The path param is bounded at the router
# boundary so out-of-range ids are rejected as a clean 422 before any DB call.
OVERFLOW_TASK_ID = 2**63  # one past signed int64 max


@pytest.mark.asyncio
async def test_get_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.get(f"/v1/tasks/{OVERFLOW_TASK_ID}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_delete_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.delete(f"/v1/tasks/{OVERFLOW_TASK_ID}")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_put_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.put(
        f"/v1/tasks/{OVERFLOW_TASK_ID}",
        json={"title": "x", "priority": 1},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_patch_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.patch(
        f"/v1/tasks/{OVERFLOW_TASK_ID}",
        json={"title": "x"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
