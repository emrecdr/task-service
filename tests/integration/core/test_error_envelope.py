"""Envelope-shape coverage for the global error handlers."""

import pytest
from app.core.config import settings
from app.core.constants import Environment
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


@pytest.mark.asyncio
async def test_dev_envelope_surfaces_original_error_in_details_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.DEV)

    crash_app = FastAPI()
    crash_app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(crash_app)

    @crash_app.get("/boom")
    async def _boom() -> None:
        raise AppError(original_error=ValueError("inner explosion"))

    transport = ASGITransport(app=crash_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")

    err = assert_error(r, 500, ErrorCode.INTERNAL_ERROR)
    assert err["details"].get("cause") == "ValueError: inner explosion"


@pytest.mark.asyncio
async def test_non_dev_envelope_omits_cause_even_with_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.PROD)

    crash_app = FastAPI()
    crash_app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(crash_app)

    @crash_app.get("/boom")
    async def _boom() -> None:
        raise AppError(original_error=ValueError("inner explosion"))

    transport = ASGITransport(app=crash_app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/boom")

    err = assert_error(r, 500, ErrorCode.INTERNAL_ERROR)
    assert "cause" not in err["details"]


@pytest.mark.asyncio
async def test_dev_duplicate_task_envelope_includes_integrity_cause(
    monkeypatch: pytest.MonkeyPatch,
    client: AsyncClient,
) -> None:
    """Caller wiring: ``_commit_or_translate`` passes the IntegrityError through."""
    monkeypatch.setattr(settings, "app_env", Environment.DEV)

    await client.post("/v1/tasks", json={"title": "same", "priority": 3})
    r = await client.post("/v1/tasks", json={"title": "same", "priority": 3})

    err = assert_error(r, 409, ErrorCode.DUPLICATE_TASK)
    assert err["details"].get("title") == "same"
    assert "IntegrityError" in err["details"].get("cause", "")
