"""Shared OpenAPI response blocks for the standard error envelope.

The task-service envelope shape (FRD §3.4) is constant across every route:

    {"error": {"code", "message", "details", "request_id"}}

Routers wire these constants via the ``responses=`` kwarg so /docs shows a
realistic body shape and an ``error.code`` example for each failure mode,
not just the bare HTTP status. The blocks here are *additive* to FastAPI's
auto-generated 422 (Pydantic's ``HTTPValidationError``) — consumers see both
shapes and the ``error.code`` field tells them which envelope is live.

Keep these in sync with ``app.core.errors.ErrorCode``. When a new error
``code`` lands in FRD §4, add an example to the matching block here.
"""

from typing import Any

from app.core.errors import ErrorCode

_ENVELOPE_DESCRIPTION = (
    "Standard error envelope (FRD §3.4). Branch on ``error.code`` for the "
    "machine-readable failure mode; ``error.message`` is human-readable and "
    "may change wording; ``error.request_id`` echoes the ``X-Request-ID`` "
    "header for log correlation."
)


def _envelope_example(code: ErrorCode, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "error": {
            "code": str(code),
            "message": message,
            "details": details,
            "request_id": "11111111-1111-1111-1111-111111111111",
        }
    }


NOT_FOUND_RESPONSE: dict[str, Any] = {
    "description": _ENVELOPE_DESCRIPTION,
    "content": {
        "application/json": {
            "example": _envelope_example(
                code=ErrorCode.TASK_NOT_FOUND,
                message="Task not found.",
                details={"id": 99999},
            ),
        },
    },
}


CONFLICT_RESPONSE: dict[str, Any] = {
    "description": _ENVELOPE_DESCRIPTION,
    "content": {
        "application/json": {
            "example": _envelope_example(
                code=ErrorCode.DUPLICATE_TASK,
                message="A task with this title already exists.",
                details={"title": "ship plan"},
            ),
        },
    },
}


VALIDATION_RESPONSE: dict[str, Any] = {
    "description": _ENVELOPE_DESCRIPTION,
    "content": {
        "application/json": {
            "examples": {
                "validation_error": {
                    "summary": "Generic Pydantic validation failure",
                    "value": _envelope_example(
                        code=ErrorCode.VALIDATION_ERROR,
                        message="Request validation failed.",
                        details={
                            "errors": [
                                {
                                    "type": "string_too_short",
                                    "loc": ["body", "title"],
                                    "msg": "String should have at least 1 character",
                                    "input": "",
                                }
                            ]
                        },
                    ),
                },
                "read_only_field": {
                    "summary": "PUT/PATCH body contained ``id`` or ``created_at``",
                    "value": _envelope_example(
                        code=ErrorCode.READ_ONLY_FIELD,
                        message="Field is server-managed and cannot be set by the caller.",
                        details={"field": "id"},
                    ),
                },
                "empty_update": {
                    "summary": "PATCH body was empty",
                    "value": _envelope_example(
                        code=ErrorCode.EMPTY_UPDATE,
                        message="PATCH body must contain at least one field.",
                        details={},
                    ),
                },
            },
        },
    },
}
