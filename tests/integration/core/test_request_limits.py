import asyncio
import json
from typing import Any

import pytest
from app.core.config import settings
from app.core.errors import ErrorCode
from app.core.middleware import BodySizeLimitMiddleware, RequestTimeoutMiddleware
from app.main import create_app
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Receive, Scope, Send

from tests.conftest import assert_error


async def _unused_app(scope: Scope, receive: Receive, send: Send) -> None:  # pragma: no cover - never invoked
    raise AssertionError("wrapped app must not be called in dispatch unit tests")


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    scope: Scope = {"type": "http", "method": "POST", "path": "/", "headers": raw, "state": {"request_id": "rid-test"}}
    return Request(scope)


class _Recorder:
    """A ``call_next`` that records whether the downstream app was reached."""

    def __init__(self) -> None:
        self.called = False

    async def __call__(self, request: Request) -> Response:
        self.called = True
        return Response(status_code=200)


def _error_body(response: Response) -> dict[str, Any]:
    return json.loads(bytes(response.body))["error"]


# --- Body size limit -------------------------------------------------------


async def test_body_over_limit_is_rejected_with_envelope() -> None:
    mw = BodySizeLimitMiddleware(_unused_app, max_bytes=1000)
    downstream = _Recorder()
    response = await mw.dispatch(_request({"content-length": "1500"}), downstream)

    assert response.status_code == 413
    assert not downstream.called
    err = _error_body(response)
    assert err["code"] == "payload_too_large"
    assert err["details"] == {"max_bytes": 1000}
    assert err["request_id"] == "rid-test"


async def test_body_under_limit_passes_through() -> None:
    mw = BodySizeLimitMiddleware(_unused_app, max_bytes=1000)
    downstream = _Recorder()
    response = await mw.dispatch(_request({"content-length": "500"}), downstream)

    assert response.status_code == 200
    assert downstream.called


async def test_body_without_content_length_passes_through() -> None:
    mw = BodySizeLimitMiddleware(_unused_app, max_bytes=1)
    downstream = _Recorder()
    response = await mw.dispatch(_request(), downstream)

    assert response.status_code == 200
    assert downstream.called


async def test_body_size_limit_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "max_request_body_bytes", 10)
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/tasks", json={"title": "a body far larger than ten bytes", "priority": 3})

    assert_error(r, 413, ErrorCode.PAYLOAD_TOO_LARGE)
    # The 413 still carries the standard request-id header (RequestID wraps it).
    assert "x-request-id" in {k.lower() for k in r.headers}


# --- Request timeout -------------------------------------------------------


async def test_slow_request_times_out_with_envelope() -> None:
    mw = RequestTimeoutMiddleware(_unused_app, timeout_seconds=0.01)

    async def _slow(_request: Request) -> Response:
        await asyncio.sleep(1)
        return Response(status_code=200)  # pragma: no cover - never reached

    response = await mw.dispatch(_request(), _slow)

    assert response.status_code == 504
    err = _error_body(response)
    assert err["code"] == "request_timeout"
    assert err["details"] == {"timeout_seconds": 0.01}
    assert err["request_id"] == "rid-test"


async def test_fast_request_passes_through() -> None:
    mw = RequestTimeoutMiddleware(_unused_app, timeout_seconds=5)
    downstream = _Recorder()
    response = await mw.dispatch(_request(), downstream)

    assert response.status_code == 200
    assert downstream.called
