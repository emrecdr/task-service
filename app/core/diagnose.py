"""Operational diagnostics: a single fail-soft ``GET /diagnose``.

Reports version/build, uptime, environment, database connectivity, and event-bus
wiring. Like the health probes it returns a **bare JSON body** (never the error
envelope) and always ``200`` — a diagnostic must not itself fail. Sensitive detail
(masked DB URL, non-secret config, dependency versions, driver error text, host
platform) is gated behind ``settings.expose_stack_traces`` (dev only), mirroring
``/readyz``: recon-safe in prod, fully informative in dev.

Adapted from the greenfield-api diagnose module, trimmed to task-service's actual
surface — no Redis/blob-storage/notification/scheduler probes for dependencies we
do not have.
"""

import platform
import time
from datetime import UTC, datetime
from functools import lru_cache
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from typing import Any, Final

from fastapi import APIRouter, Request
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.core.config import settings
from app.core.database import probe_database
from app.core.datetime_utils import iso_z
from app.core.dependencies import SessionDep
from app.core.event_bus import EventBus

router = APIRouter(tags=["operational"])

# Monotonic stamp captured at import (≈ process start) for uptime.
_STARTED_AT: Final[float] = time.monotonic()

# Runtime deps surfaced in dev diagnostics.
_TRACKED_PACKAGES: Final[tuple[str, ...]] = (
    "fastapi",
    "pydantic",
    "sqlmodel",
    "sqlalchemy",
    "asyncpg",
    "alembic",
    "uvicorn",
    "structlog",
)


@lru_cache
def _dependency_versions() -> dict[str, str]:
    # Package versions are constant for the process lifetime — resolve the metadata once.
    versions: dict[str, str] = {}
    for name in _TRACKED_PACKAGES:
        try:
            versions[name] = pkg_version(name)
        except PackageNotFoundError:  # pragma: no cover - all are installed deps
            versions[name] = "unknown"
    return versions


def _config_overview() -> dict[str, Any]:
    """Non-secret configuration snapshot (dev-gated). No URLs, credentials, or hosts."""
    return {
        "api_prefix": settings.api_prefix,
        "json_logs": settings.json_logs,
        "cors_allow_origins": settings.cors_allow_origins,
        "max_request_body_bytes": settings.max_request_body_bytes,
        "request_timeout_seconds": settings.request_timeout_seconds,
    }


async def _database_probe(session: AsyncSession, *, detailed: bool) -> dict[str, Any]:
    """Fail-soft ``SELECT 1`` (shared ``probe_database``). Reports ``ok``/``unavailable`` +
    duration; driver error text and the (password-masked) URL only when ``detailed``."""
    result: dict[str, Any] = {}
    start = time.perf_counter()
    err = await probe_database(session)
    result["status"] = "ok" if err is None else "unavailable"
    if err is not None and detailed:
        result["error"] = str(err)
    result["duration_ms"] = round((time.perf_counter() - start) * 1000, 2)
    if detailed:
        result["url"] = make_url(settings.database_url).render_as_string(hide_password=True)
    return result


@router.get(
    "/diagnose",
    summary="Operational diagnostics (fail-soft; detail gated to dev)",
    responses={200: {"description": "Diagnostic snapshot. Always 200 — a probe must not fail."}},
)
async def diagnose(request: Request, session: SessionDep) -> dict[str, Any]:
    detailed = settings.expose_stack_traces

    database = await _database_probe(session, detailed=detailed)

    bus = getattr(request.app.state, "event_bus", None)
    subscriptions = bus.subscriptions() if isinstance(bus, EventBus) else {}

    version: dict[str, str] = {"app": __version__}
    if detailed:
        version["python"] = platform.python_version()
        version["implementation"] = platform.python_implementation()
        version["platform"] = platform.platform()

    body: dict[str, Any] = {
        "status": "ok" if database["status"] == "ok" else "degraded",
        "timestamp": iso_z(datetime.now(UTC)),
        "environment": settings.app_env,
        "version": version,
        "uptime_seconds": round(time.monotonic() - _STARTED_AT, 2),
        "database": database,
        "event_bus": {"event_types": len(subscriptions), "handlers": sum(subscriptions.values())},
    }
    if detailed:
        body["dependencies"] = _dependency_versions()
        body["config"] = _config_overview()
    return body
