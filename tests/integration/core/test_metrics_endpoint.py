from httpx import AsyncClient


async def test_metrics_endpoint_exposes_prometheus_format(client: AsyncClient) -> None:
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    # The instrumentator's default RED metrics are present in the exposition.
    assert "http_request" in r.text


async def test_metrics_endpoint_is_not_in_openapi_schema(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/metrics" not in schema["paths"]
