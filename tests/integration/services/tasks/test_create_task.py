import uuid

from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


async def test_create_returns_201_with_envelope(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "ship plan", "priority": 4})
    assert r.status_code == 201
    body = r.json()
    assert uuid.UUID(body["id"]).version == 7  # public id is a UUIDv7
    assert body["title"] == "ship plan"
    assert body["status"] == "new"
    assert body["priority"] == 4
    assert body["created_at"].endswith("Z")


async def test_create_strips_title_whitespace(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "  ship plan  ", "priority": 4})
    assert r.status_code == 201
    assert r.json()["title"] == "ship plan"


async def test_create_duplicate_title_returns_409_with_code(client: AsyncClient) -> None:
    await client.post("/v1/tasks", json={"title": "alpha", "priority": 1})
    r = await client.post("/v1/tasks", json={"title": "  ALPHA  ", "priority": 1})
    assert_error(r, 409, ErrorCode.DUPLICATE_TASK, details={"title": "  ALPHA  "})


async def test_create_empty_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "", "priority": 1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_whitespace_only_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "   ", "priority": 1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_server_owned_id(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        json={"id": 99, "title": "x", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "id"})


async def test_create_rejects_priority_above_max(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 9})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_priority_below_min(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 0})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_priority_negative(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": -1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_malformed_json_body_returns_422_envelope(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        content=b"\xff\xfe not json",
        headers={"Content-Type": "application/json"},
    )
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_nul_byte_in_title(client: AsyncClient) -> None:
    # Postgres text can't store a NUL (0x00); reject at the boundary as 422, not a 500.
    r = await client.post("/v1/tasks", json={"title": "a\x00b", "priority": 1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_nul_byte_in_description(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "ok", "priority": 1, "description": "x\x00y"})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_rejects_nul_byte_in_status(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "ok", "priority": 1, "status": "n\x00ew"})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_create_with_explicit_entry_status_persists_it(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 2, "status": "in_progress"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "in_progress"
    fetched = await client.get(f"/v1/tasks/{r.json()['id']}")
    assert fetched.json()["status"] == "in_progress"
