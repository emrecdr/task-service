from typing import Any, Final

from app.core.errors import ErrorCode

_ENVELOPE_DESCRIPTION: Final[str] = (
    "Standard error envelope. Branch on ``error.code`` for the machine-readable "
    "failure mode; ``error.message`` is human-readable and may change wording; "
    "``error.request_id`` echoes the ``X-Request-ID`` header for log correlation."
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


NOT_FOUND_RESPONSE: Final[dict[str, Any]] = {
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


CONFLICT_RESPONSE: Final[dict[str, Any]] = {
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


VALIDATION_RESPONSE: Final[dict[str, Any]] = {
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
