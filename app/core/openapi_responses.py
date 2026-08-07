from typing import Any, Final

from app.core.errors import ErrorCode, ErrorDetail, ErrorEnvelope

_ENVELOPE_DESCRIPTION: Final[str] = (
    "Standard error envelope. Branch on ``error.code`` for the machine-readable "
    "failure mode; ``error.message`` is human-readable and may change wording; "
    "``error.request_id`` echoes the ``X-Request-ID`` header for log correlation."
)


def _envelope_example(code: ErrorCode, message: str, details: dict[str, Any]) -> dict[str, Any]:
    """Build a docs example straight from the ``ErrorEnvelope`` schema so examples cannot drift from it."""
    return ErrorEnvelope(
        error=ErrorDetail(
            code=str(code),
            message=message,
            details=details,
            request_id="11111111-1111-1111-1111-111111111111",
        )
    ).model_dump()


def _envelope_response(
    *,
    example: dict[str, Any] | None = None,
    examples: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A response entry: the ``ErrorEnvelope`` schema plus a single ``example`` or named ``examples``."""
    media: dict[str, Any] = {"example": example} if example is not None else {"examples": examples}
    return {
        "model": ErrorEnvelope,
        "description": _ENVELOPE_DESCRIPTION,
        "content": {"application/json": media},
    }


# ---- Reusable 422 example entries, composed per route so each lists only its reachable codes ----

_VALIDATION_ERROR_EXAMPLE: Final[dict[str, Any]] = {
    "summary": "Request failed schema validation (body, query, or path parameter)",
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
}

_UNKNOWN_STATUS_EXAMPLE: Final[dict[str, Any]] = {
    "summary": "Status in the body is not a state of the active workflow",
    "value": _envelope_example(
        code=ErrorCode.UNKNOWN_STATUS,
        message="Unknown workflow state.",
        details={"field": "status", "value": "ghost", "known_states": ["new", "in_progress", "completed"]},
    ),
}

_READ_ONLY_FIELD_EXAMPLE: Final[dict[str, Any]] = {
    "summary": "Body set a server-managed field (``id`` or ``created_at``)",
    "value": _envelope_example(
        code=ErrorCode.READ_ONLY_FIELD,
        message="Field is server-managed and cannot be set by the caller.",
        details={"field": "id"},
    ),
}

_EMPTY_UPDATE_EXAMPLE: Final[dict[str, Any]] = {
    "summary": "PATCH body contained no fields",
    "value": _envelope_example(
        code=ErrorCode.EMPTY_UPDATE,
        message="PATCH body must contain at least one field.",
        details={},
    ),
}


# ---- 404 (any /tasks/{id} route) ----

NOT_FOUND_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    example=_envelope_example(
        code=ErrorCode.TASK_NOT_FOUND,
        message="Task not found.",
        details={"id": 99999},
    ),
)


# ---- 403 (task create / replace / patch — workflow role guard) ----

FORBIDDEN_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    example=_envelope_example(
        code=ErrorCode.TRANSITION_FORBIDDEN,
        message="You do not have a role permitted to make this transition.",
        details={"transition": "Approve", "required_roles": ["manager"], "actor_roles": []},
    ),
)


# ---- 409 (task create / replace / patch) ----

CONFLICT_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={
        "duplicate_task": {
            "summary": "Another task already uses this title",
            "value": _envelope_example(
                code=ErrorCode.DUPLICATE_TASK,
                message="A task with this title already exists.",
                details={"title": "ship plan"},
            ),
        },
        "invalid_transition": {
            "summary": "The active workflow does not allow this status move",
            "value": _envelope_example(
                code=ErrorCode.INVALID_TRANSITION,
                message="The active workflow does not allow this move.",
                details={"from": "new", "to": "completed", "allowed": ["in_progress"]},
            ),
        },
        "wip_limit_exceeded": {
            "summary": "The target state is at its work-in-progress limit",
            "value": _envelope_example(
                code=ErrorCode.WIP_LIMIT_EXCEEDED,
                message="The target state is at its work-in-progress limit.",
                details={"state": "in_progress", "limit": 3, "current": 3},
            ),
        },
    },
)


# ---- 409 (tag delete) ----

TAG_CONFLICT_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={
        "tag_in_use": {
            "summary": "Tasks still carry this tag",
            "value": _envelope_example(
                code=ErrorCode.TAG_IN_USE,
                message="Tag is still applied to one or more tasks.",
                details={"id": "0199a5f2-9c1e-7c2a-8f3b-1d2e3f4a5b6c", "name": "urgent", "task_count": 4},
            ),
        },
    },
)


# ---- 422 variants, each listing only the codes reachable on its routes ----

# Path / query validation only: GET one, GET list, DELETE, GET transitions.
VALIDATION_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={"validation_error": _VALIDATION_ERROR_EXAMPLE},
)

# Body writes that create or fully replace a task: POST, PUT.
WRITE_VALIDATION_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={
        "validation_error": _VALIDATION_ERROR_EXAMPLE,
        "unknown_status": _UNKNOWN_STATUS_EXAMPLE,
        "read_only_field": _READ_ONLY_FIELD_EXAMPLE,
    },
)

# PATCH additionally rejects an empty body.
PATCH_VALIDATION_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={
        "validation_error": _VALIDATION_ERROR_EXAMPLE,
        "unknown_status": _UNKNOWN_STATUS_EXAMPLE,
        "read_only_field": _READ_ONLY_FIELD_EXAMPLE,
        "empty_update": _EMPTY_UPDATE_EXAMPLE,
    },
)


# ---- Workflow admin (PUT /v1/workflow) ----

WORKFLOW_CONFLICT_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    example=_envelope_example(
        code=ErrorCode.WORKFLOW_STATES_IN_USE,
        message="Definition would leave existing tasks in states it does not define.",
        details={"states": {"in_progress": 3}},
    ),
)

WORKFLOW_VALIDATION_RESPONSE: Final[dict[str, Any]] = _envelope_response(
    examples={
        "invalid_workflow_definition": {
            "summary": "Definition content failed validation (all problems listed)",
            "value": _envelope_example(
                code=ErrorCode.INVALID_WORKFLOW_DEFINITION,
                message="Workflow definition is invalid.",
                details={"errors": ["states[1]: duplicate state 'todo'"]},
            ),
        },
        "validation_error": {
            "summary": "Request body is not a JSON object",
            "value": _envelope_example(
                code=ErrorCode.VALIDATION_ERROR,
                message="Request validation failed.",
                details={
                    "errors": [
                        {
                            "type": "dict_type",
                            "loc": ["body"],
                            "msg": "Input should be a valid dictionary",
                            "input": [],
                        }
                    ]
                },
            ),
        },
    },
)
