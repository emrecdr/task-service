from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


async def _seed(client: AsyncClient) -> None:
    payloads = [
        {"title": "a", "priority": 1, "status": "new"},
        {"title": "b", "priority": 5, "status": "in_progress"},
        {"title": "c", "priority": 3, "status": "completed"},
        {"title": "d", "priority": 2, "status": "new"},
    ]
    for p in payloads:
        r = await client.post("/v1/tasks", json=p)
        assert r.status_code == 201


async def test_list_returns_envelope_shape(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"items", "total", "limit", "offset"}
    assert body["total"] == 4
    assert body["limit"] == 100
    assert body["offset"] == 0
    assert len(body["items"]) == 4


async def test_list_default_sort_is_priority_desc(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks")
    priorities = [t["priority"] for t in r.json()["items"]]
    assert priorities == sorted(priorities, reverse=True)


async def test_list_sort_priority_asc(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks?order_by=priority&order_dir=asc")
    priorities = [t["priority"] for t in r.json()["items"]]
    assert priorities == sorted(priorities)


async def test_list_filter_by_status_multivalue(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks?status=new&status=completed")
    body = r.json()
    statuses = {t["status"] for t in body["items"]}
    assert statuses == {"new", "completed"}
    assert body["total"] == 3


async def test_list_pagination(client: AsyncClient) -> None:
    """Seeded priorities are 5,3,2,1 — offset=1, limit=2 desc must return the middle window."""
    await _seed(client)
    r = await client.get("/v1/tasks?limit=2&offset=1&order_by=priority&order_dir=desc")
    body = r.json()
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert body["total"] == 4
    priorities = [t["priority"] for t in body["items"]]
    assert priorities == [3, 2]
    titles = [t["title"] for t in body["items"]]
    assert titles == ["c", "d"]


async def test_list_pagination_offset_zero_returns_top_of_window(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks?limit=2&offset=0&order_by=priority&order_dir=desc")
    body = r.json()
    priorities = [t["priority"] for t in body["items"]]
    assert priorities == [5, 3]


async def test_list_pagination_offset_past_end_returns_empty_items(client: AsyncClient) -> None:
    await _seed(client)
    r = await client.get("/v1/tasks?limit=2&offset=10")
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 4


async def test_list_limit_above_max_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks?limit=10000")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_list_negative_offset_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks?offset=-1")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_list_unknown_status_returns_422(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks?status=bogus")
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_list_empty_returns_zero_total(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
