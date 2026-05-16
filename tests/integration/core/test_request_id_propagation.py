import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_is_generated_when_absent(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert "x-request-id" in {k.lower() for k in r.headers}
    assert r.headers["x-request-id"]  # non-empty


@pytest.mark.asyncio
async def test_request_id_is_echoed_when_provided(client: AsyncClient) -> None:
    given = "11111111-1111-1111-1111-111111111111"
    r = await client.get("/healthz", headers={"X-Request-ID": given})
    assert r.status_code == 200
    assert r.headers["x-request-id"] == given


@pytest.mark.asyncio
async def test_request_id_present_in_error_envelope(client: AsyncClient) -> None:
    given = "22222222-2222-2222-2222-222222222222"
    r = await client.get("/v1/tasks/99999", headers={"X-Request-ID": given})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["request_id"] == given
    assert r.headers["x-request-id"] == given
