"""Liveness and readiness endpoints (FRD §7, TIS §7.5).

``/healthz`` returns ``200`` whenever the process is running — synchronous,
no I/O. ``/readyz`` returns ``200`` only when a trivial repository round-trip
succeeds; ``503`` otherwise. Container orchestrators key traffic routing off
``/readyz``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, OperationalError
from sqlmodel import Session

from app.core.dependencies import get_session

router = APIRouter(tags=["operational"])


@router.get("/healthz")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
def readiness(session: Session = Depends(get_session)) -> JSONResponse | dict[str, str]:
    try:
        session.scalar(text("SELECT 1"))
    except (OperationalError, DatabaseError) as err:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(err)},
        )
    return {"status": "ready"}
