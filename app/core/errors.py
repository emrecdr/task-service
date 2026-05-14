"""Error code enum, ``AppError`` hierarchy, and global FastAPI exception handlers.

All three concerns are colocated because they always change together (TIS §7.1).
The handler converts both :class:`AppError` subclasses *and* Pydantic
:class:`RequestValidationError` into the same JSON envelope (FRD §3.4), so
consumers can switch on ``error.code`` without parsing English strings.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    EMPTY_UPDATE = "empty_update"
    READ_ONLY_FIELD = "read_only_field"
    DUPLICATE_TASK = "duplicate_task"
    TASK_NOT_FOUND = "task_not_found"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    """Base class for every domain-typed exception.

    Subclasses set ``status_code``, ``error_code``, and the default ``detail``
    string. Callers pass per-instance ``details`` (a dict of arbitrary context
    that ends up in the error envelope's ``details`` field).
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected internal server error occurred."
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(
        self,
        *,
        detail: str | None = None,
        details: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        if detail is not None:
            self.detail = detail
        self.details: dict[str, Any] = details or {}
        self.original_error = original_error
        super().__init__(self.detail)


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = ErrorCode.VALIDATION_ERROR


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


# Fields the server owns — callers must not set these via PUT/PATCH bodies.
_SERVER_OWNED_FIELDS = frozenset({"id", "created_at"})


def _envelope(
    *,
    request: Request,
    code: ErrorCode,
    message: str,
    details: dict[str, Any],
    status_code: int,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": str(code),
                "message": message,
                "details": details,
                "request_id": getattr(request.state, "request_id", None),
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the global handlers for ``AppError`` and Pydantic validation errors."""

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return _envelope(
            request=request,
            code=exc.error_code,
            message=exc.detail,
            details=exc.details,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Detect attempts to set server-owned fields (id, created_at) on a
        # PUT/PATCH body — they manifest as ``extra_forbidden`` errors because
        # the DTOs use ``model_config = ConfigDict(extra="forbid")``.
        for err in exc.errors():
            loc = err.get("loc", ())
            if err.get("type") == "extra_forbidden" and loc and loc[-1] in _SERVER_OWNED_FIELDS:
                return _envelope(
                    request=request,
                    code=ErrorCode.READ_ONLY_FIELD,
                    message="Field is server-managed and cannot be set by the caller.",
                    details={"field": loc[-1]},
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        return _envelope(
            request=request,
            code=ErrorCode.VALIDATION_ERROR,
            message="Request validation failed.",
            details={"errors": exc.errors()},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
