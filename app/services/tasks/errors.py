from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError


class DuplicateTaskError(ConflictError):
    error_code = ErrorCode.DUPLICATE_TASK
    detail = "A task with this title already exists."


class InvalidTransitionError(ConflictError):
    error_code = ErrorCode.INVALID_TRANSITION
    detail = "The active workflow does not allow this move."


class TaskNotFoundError(NotFoundError):
    error_code = ErrorCode.TASK_NOT_FOUND
    detail = "Task not found."


class EmptyUpdateError(ValidationError):
    error_code = ErrorCode.EMPTY_UPDATE
    detail = "PATCH body must contain at least one field."
