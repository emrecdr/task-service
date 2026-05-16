"""Envelope-shape coverage for the global error handlers."""

import pytest
from app.core.errors import AppError, ErrorCode, register_exception_handlers
from app.core.middleware import RequestIDMiddleware
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.conftest import assert_error


@pytest.mark.asyncio
async def test_404_envelope_shape(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/99999")
    err = assert_error(r, 404, ErrorCode.TASK_NOT_FOUND, details={"id": 99999})
    assert "message" in err


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

    err = assert_error(r, 500, ErrorCode.INTERNAL_ERROR)
    assert "message" in err


@pytest.mark.asyncio
async def test_validation_error_envelope_shape(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": "not-int"})
    err = assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
    assert "errors" in err["details"]
