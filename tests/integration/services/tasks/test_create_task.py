import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_returns_201_with_envelope(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "ship plan", "priority": 4})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["title"] == "ship plan"
    assert body["status"] == "new"
    assert body["priority"] == 4
    # FRD §2.4: created_at must be RFC 3339 with explicit ``Z`` UTC marker
    # (TaskResponse._serialize_created_at normalises ``+00:00`` → ``Z``).
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
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "duplicate_task"
    assert "request_id" in err
    assert err["details"] == {"title": "  ALPHA  "}


@pytest.mark.asyncio
async def test_create_empty_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "", "priority": 1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_whitespace_only_title_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "   ", "priority": 1})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_rejects_server_owned_id(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        json={"id": 99, "title": "x", "priority": 1},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "read_only_field"
    assert err["details"] == {"field": "id"}


@pytest.mark.asyncio
async def test_create_rejects_priority_out_of_range(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 9})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


# Malformed JSON body (non-decodable bytes) used to surface as Starlette's
# default 400 ``{"detail": "There was an error parsing the body"}``, bypassing
# the FRD §3.4 single-envelope contract. A dedicated handler re-wraps it as
# the canonical 422 ``validation_error`` envelope.
@pytest.mark.asyncio
async def test_create_malformed_json_body_returns_422_envelope(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/tasks",
        content=b"\xff\xfe not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert "request_id" in err
