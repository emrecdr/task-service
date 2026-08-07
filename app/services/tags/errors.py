from app.core.errors import ConflictError, ErrorCode, NotFoundError


class TagNotFoundError(NotFoundError):
    error_code = ErrorCode.TAG_NOT_FOUND
    detail = "Tag not found."


class TagInUseError(ConflictError):
    error_code = ErrorCode.TAG_IN_USE
    detail = "Tag is still applied to one or more tasks."
