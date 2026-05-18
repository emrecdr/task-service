import json
from typing import Never

import pytest
from app.core.config import settings
from app.core.constants import Environment
from app.core.health import readiness
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError


async def test_healthz_returns_ok(client: AsyncClient) -> None:
    r = await client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readyz_returns_ready_when_db_is_reachable(client: AsyncClient) -> None:
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


class _FailingSession:
    def scalar(self, _stmt: object) -> Never:
        raise OperationalError("SELECT 1", None, Exception("boom"))


async def test_readyz_in_dev_surfaces_db_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.DEV)
    response = await readiness(_FailingSession())  # type: ignore[arg-type]

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = json.loads(bytes(response.body))
    assert body["status"] == "not_ready"
    assert "boom" in body["error"]


async def test_readyz_outside_dev_omits_db_error_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.PROD)
    response = await readiness(_FailingSession())  # type: ignore[arg-type]

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    body = json.loads(bytes(response.body))
    assert body == {"status": "not_ready"}
