"""``GET /v1/tags`` and ``DELETE /v1/tags/{id}`` — FRD §3.1, plus the envelope for both tag
error codes in §4."""

import uuid

from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import assert_error


async def _tag_id(client: AsyncClient, name: str) -> str:
    """Create a tag by using it, then read back its id."""
    r = await client.post("/v1/tasks", json={"title": f"holder-{name}", "priority": 3, "tags": [name]})
    assert r.status_code == 201, r.text
    listed = (await client.get("/v1/tags")).json()["items"]
    return str(next(t["id"] for t in listed if t["name"] == name))


class TestList:
    async def test_empty_vocabulary(self, client: AsyncClient) -> None:
        r = await client.get("/v1/tags")

        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0}

    async def test_reports_task_counts_and_sorts_by_name(self, client: AsyncClient) -> None:
        await client.post("/v1/tasks", json={"title": "a", "priority": 3, "tags": ["zebra", "alpha"]})
        await client.post("/v1/tasks", json={"title": "b", "priority": 3, "tags": ["alpha"]})

        body = (await client.get("/v1/tags")).json()

        assert [t["name"] for t in body["items"]] == ["alpha", "zebra"]
        assert {t["name"]: t["task_count"] for t in body["items"]} == {"alpha": 2, "zebra": 1}
        assert body["total"] == 2

    async def test_a_freed_tag_stays_listed_with_a_zero_count(self, client: AsyncClient) -> None:
        r = await client.post("/v1/tasks", json={"title": "a", "priority": 3, "tags": ["temp"]})
        await client.patch(f"/v1/tasks/{r.json()['id']}", json={"tags": []})

        body = (await client.get("/v1/tags")).json()

        # Still vocabulary, just unused — which is exactly the tag an operator wants to delete.
        assert body["items"][0]["task_count"] == 0


class TestDelete:
    async def test_unused_tag_is_deleted(self, client: AsyncClient) -> None:
        tag_id = await _tag_id(client, "spare")
        holder = (await client.get("/v1/tasks")).json()["items"][0]["id"]
        await client.patch(f"/v1/tasks/{holder}", json={"tags": []})

        assert (await client.delete(f"/v1/tags/{tag_id}")).status_code == 204
        assert (await client.get("/v1/tags")).json()["total"] == 0

    async def test_tag_in_use_returns_409_envelope_with_the_count(self, client: AsyncClient) -> None:
        tag_id = await _tag_id(client, "busy")
        await client.post("/v1/tasks", json={"title": "second", "priority": 3, "tags": ["busy"]})

        r = await client.delete(f"/v1/tags/{tag_id}")

        err = assert_error(r, 409, ErrorCode.TAG_IN_USE)
        assert err["details"]["task_count"] == 2
        assert err["details"]["name"] == "busy"
        # Refused means untouched.
        assert (await client.get("/v1/tags")).json()["total"] == 1

    async def test_unknown_tag_returns_404_envelope(self, client: AsyncClient) -> None:
        r = await client.delete(f"/v1/tags/{uuid.uuid7()}")

        assert_error(r, 404, ErrorCode.TAG_NOT_FOUND)

    async def test_malformed_id_returns_422_envelope(self, client: AsyncClient) -> None:
        r = await client.delete("/v1/tags/not-a-uuid")

        assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
