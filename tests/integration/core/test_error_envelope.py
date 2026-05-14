"""Envelope-shape coverage for the global error handlers.

Includes the ``internal_error`` path: a route raises ``AppError`` directly
(the base class defaults to ``status_code=500`` and
``error_code=ErrorCode.INTERNAL_ERROR``), and the global handler converts it
to the standard envelope. This is the only ``ErrorCode`` value that no
domain-level ``raise`` reaches naturally, so it needs a synthetic route.
"""

import pytest
from app.core.errors import AppError, register_exception_handlers
from app.core.middleware import RequestIDMiddleware
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_404_envelope_shape(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/99999")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "task_not_found"
    assert err["details"] == {"id": 99999}
    assert "message" in err
    assert "request_id" in err


@pytest.mark.asyncio
async def test_internal_error_envelope_shape() -> None:
    crash_app = FastAPI()
    crash_app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(crash_app)

    @crash_app.get("/boom")
    async def _boom() -> None:
        raise AppError()

    transport = ASGITransport(app=crash_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")

    assert r.status_code == 500
    err = r.json()["error"]
    assert err["code"] == "internal_error"
    assert "message" in err
    assert err["request_id"]


@pytest.mark.asyncio
async def test_validation_error_envelope_shape(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": "not-int"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert "errors" in err["details"]
