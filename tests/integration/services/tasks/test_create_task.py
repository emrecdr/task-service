import pytest
from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


@pytest.mark.asyncio
async def test_create_returns_201_with_envelope(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "ship plan", "priority": 4})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["title"] == "ship plan"
    assert body["status"] == "new"
    assert body["priority"] == 4
    assert body["created_at"].endswith("Z")


@pytest.mark.asyncio
async def test_create_strips_title_whitespace(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "  ship plan  ", "priority": 4})
    assert r.status_code == 201
    assert r.json()["title"] == "ship plan"


@pytest.mark.asyncio
async def test_create_duplicate_title_returns_409_with_code(client: AsyncClient) -> None:
    await client.post("/v1/tasks", json={"title": "alpha", "priority": 1})
    r = await client.post("/v1/tasks", json={"title": "  ALPHA  ", "priority": 1})
    assert_error(r, 409, ErrorCode.DUPLICATE_TASK, details={"title": "  ALPHA  "})


@pytest.mark.asyncio
async def test_create_empty_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "", "priority": 1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_create_whitespace_only_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "   ", "priority": 1})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_create_rejects_server_owned_id(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        json={"id": 99, "title": "x", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "id"})


@pytest.mark.asyncio
async def test_create_rejects_priority_out_of_range(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 9})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


@pytest.mark.asyncio
async def test_create_malformed_json_body_returns_422_envelope(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        content=b"\xff\xfe not json",
        headers={"Content-Type": "application/json"},
    )
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
