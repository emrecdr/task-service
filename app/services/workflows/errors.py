from app.core.errors import ConflictError, ErrorCode, ValidationError


class WorkflowValidationError(ValidationError):
    """A workflow definition failed validation; ``errors`` lists every problem found."""

    error_code = ErrorCode.INVALID_WORKFLOW_DEFINITION
    detail = "Workflow definition is invalid."

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(details={"errors": errors})
        # ``str(exc)`` lists every problem (tracebacks, pytest.raises match);
        # the envelope keeps the short ``detail`` + machine-readable details.
        self.args = ("Workflow definition is invalid:\n" + "\n".join(f"  - {e}" for e in errors),)


class WorkflowStatesInUseError(ConflictError):
    error_code = ErrorCode.WORKFLOW_STATES_IN_USE
    detail = "Definition would leave existing tasks in states it does not define."
