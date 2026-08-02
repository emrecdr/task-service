from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error

# A well-formed UUID that will never exist — for 404 (not-found) paths. Distinct from a
# malformed path segment, which is rejected as 422 by UUID validation.
_MISSING_ID = "00000000-0000-0000-0000-000000000000"


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


async def test_get_unknown_id_returns_404_envelope(client: AsyncClient) -> None:
    r = await client.get(f"/v1/tasks/{_MISSING_ID}")
    err = assert_error(r, 404, ErrorCode.TASK_NOT_FOUND, details={"id": _MISSING_ID})
    assert "message" in err


async def test_get_non_uuid_id_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/not-a-uuid")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
