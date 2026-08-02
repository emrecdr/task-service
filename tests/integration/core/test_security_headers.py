import pytest
from app.core.config import settings
from app.core.constants import Environment
from app.core.middleware import SecurityHeadersMiddleware
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send


async def _unused_app(scope: Scope, receive: Receive, send: Send) -> None:  # pragma: no cover - never invoked
    raise AssertionError("wrapped app must not be called in dispatch unit tests")


async def _ok(_request: Request) -> Response:
    return Response(status_code=200)


def _request() -> Request:
    scope: Scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "state": {"request_id": "rid-test"}}
    return Request(scope)


async def test_security_headers_present_on_success(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"


async def test_security_headers_present_on_error_envelope(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


async def test_hsts_absent_outside_prod(client: AsyncClient) -> None:
    # Default APP_ENV=test → HSTS must not be advertised (it is HTTPS-only).
    r = await client.get("/healthz")
    assert "strict-transport-security" not in {k.lower() for k in r.headers}


async def test_hsts_added_when_enabled() -> None:
    mw = SecurityHeadersMiddleware(_unused_app, hsts_enabled=True)
    response = await mw.dispatch(_request(), _ok)
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


async def test_hsts_omitted_when_disabled() -> None:
    mw = SecurityHeadersMiddleware(_unused_app, hsts_enabled=False)
    response = await mw.dispatch(_request(), _ok)
    assert "strict-transport-security" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


async def test_cors_disabled_by_default(client: AsyncClient) -> None:
    # Empty allow-list (the default) means no CORS middleware and no ACAO header.
    r = await client.get("/healthz", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


async def test_cors_allows_configured_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    origin = "https://app.example.com"
    monkeypatch.setattr(settings, "cors_allow_origins", [origin])
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/healthz", headers={"Origin": origin})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin


async def test_hsts_present_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.PROD)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/healthz")
    assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"
