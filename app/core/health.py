from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import probe_database
from app.core.dependencies import SessionDep

router = APIRouter(tags=["operational"])

# Ops probes return a bare ``{"status": ...}`` body, deliberately NOT the API
# error envelope: liveness/readiness are infra signals, not resource errors.
_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"status": {"type": "string"}},
    "required": ["status"],
}
_READINESS_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Database reachable; the service can serve traffic.",
        "content": {"application/json": {"schema": _STATUS_SCHEMA, "example": {"status": "ready"}}},
    },
    503: {
        "description": "Database unreachable; the service is not ready. The driver error "
        "text is included only when ``expose_stack_traces`` is enabled (non-prod).",
        "content": {"application/json": {"schema": _STATUS_SCHEMA, "example": {"status": "not_ready"}}},
    },
}


@router.get(
    "/healthz",
    responses={
        200: {
            "description": "The process is alive.",
            "content": {"application/json": {"schema": _STATUS_SCHEMA, "example": {"status": "ok"}}},
        },
    },
)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz", response_model=None, responses=_READINESS_RESPONSES)
async def readiness(session: SessionDep) -> JSONResponse | dict[str, str]:
    err = await probe_database(session)
    if err is not None:
        # Raw driver error text can leak host/db/credentials — gate on the same dev flag as AppError envelopes.
        content: dict[str, str] = {"status": "not_ready"}
        if settings.expose_stack_traces:
            content["error"] = str(err)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=content,
        )
    return {"status": "ready"}
