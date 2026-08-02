# pyright: reportPrivateUsage=false
"""Diagnose endpoint: DB-independent helper tests + endpoint behaviour."""

from typing import Never

import pytest
from app.core.config import settings
from app.core.constants import Environment
from app.core.diagnose import _config_overview, _database_probe, _dependency_versions
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError


class _FailingSession:
    async def scalar(self, _stmt: object) -> Never:
        raise OperationalError("SELECT 1", None, Exception("boom"))


async def test_database_probe_reports_unavailable_and_hides_detail_by_default() -> None:
    probe = await _database_probe(_FailingSession(), detailed=False)  # type: ignore[arg-type]
    assert probe["status"] == "unavailable"
    assert "error" not in probe
    assert "url" not in probe
    assert isinstance(probe["duration_ms"], float)


async def test_database_probe_surfaces_error_and_masked_url_when_detailed() -> None:
    probe = await _database_probe(_FailingSession(), detailed=True)  # type: ignore[arg-type]
    assert probe["status"] == "unavailable"
    assert "boom" in probe["error"]
    assert "***" in probe["url"]  # password masked in the surfaced URL


def test_dependency_versions_resolves_installed_packages() -> None:
    versions = _dependency_versions()
    assert versions["fastapi"] != "unknown"
    assert "sqlalchemy" in versions
    assert "asyncpg" in versions


def test_config_overview_excludes_secrets_and_urls() -> None:
    cfg = _config_overview()
    assert cfg["api_prefix"] == "/v1"
    assert not any(k.lower().endswith("url") or "password" in k.lower() or "secret" in k.lower() for k in cfg)


async def test_diagnose_endpoint_ok_when_db_reachable(client: AsyncClient) -> None:
    r = await client.get("/diagnose")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]["app"]
    assert body["database"]["status"] == "ok"
    assert body["environment"] == "test"
    assert "event_types" in body["event_bus"]


async def test_diagnose_detail_gated_outside_dev(client: AsyncClient) -> None:
    # APP_ENV=test → expose_stack_traces False → no config/deps/masked-url leak.
    body = (await client.get("/diagnose")).json()
    assert "config" not in body
    assert "dependencies" not in body
    assert "url" not in body["database"]


async def test_diagnose_detail_present_in_dev(monkeypatch: pytest.MonkeyPatch, client: AsyncClient) -> None:
    monkeypatch.setattr(settings, "app_env", Environment.DEV)
    body = (await client.get("/diagnose")).json()
    assert "config" in body
    assert "dependencies" in body
    assert "url" in body["database"]
