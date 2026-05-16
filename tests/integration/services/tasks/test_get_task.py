import pytest
from app.core.constants import INT64_MAX
from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


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
    err = assert_error(r, 404, ErrorCode.TASK_NOT_FOUND, details={"id": 99999})
    assert "message" in err


@pytest.mark.asyncio
async def test_get_non_integer_id_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/not-an-int")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


OVERFLOW_TASK_ID = INT64_MAX + 1


@pytest.mark.asyncio
async def test_get_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.get(f"/v1/tasks/{OVERFLOW_TASK_ID}")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_delete_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.delete(f"/v1/tasks/{OVERFLOW_TASK_ID}")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_put_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.put(
        f"/v1/tasks/{OVERFLOW_TASK_ID}",
        json={"title": "x", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_patch_overflow_id_returns_422(client: AsyncClient) -> None:
    r = await client.patch(
        f"/v1/tasks/{OVERFLOW_TASK_ID}",
        json={"title": "x"},
    )
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
