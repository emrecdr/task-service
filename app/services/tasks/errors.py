"""Domain exceptions for the tasks feature."""

from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError


class DuplicateTaskError(ConflictError):
    error_code = ErrorCode.DUPLICATE_TASK
    detail = "A task with this title already exists."


class TaskNotFoundError(NotFoundError):
    error_code = ErrorCode.TASK_NOT_FOUND
    detail = "Task not found."


class EmptyUpdateError(ValidationError):
    error_code = ErrorCode.EMPTY_UPDATE
    detail = "PATCH body must contain at least one field."


class ReadOnlyFieldError(ValidationError):
    error_code = ErrorCode.READ_ONLY_FIELD
    detail = "Field is server-managed and cannot be set by the caller."
