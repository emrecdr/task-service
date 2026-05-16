"""Liveness (``/healthz``) and readiness (``/readyz``) endpoints."""

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, OperationalError

from app.core.dependencies import SessionDep

router = APIRouter(tags=["operational"])


@router.get("/healthz")
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None)
async def readiness(session: SessionDep) -> JSONResponse | dict[str, str]:
    try:
        session.scalar(text("SELECT 1"))
    except (OperationalError, DatabaseError) as err:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not_ready", "error": str(err)},
        )
    return {"status": "ready"}
