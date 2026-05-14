"""Request and response DTOs for the tasks feature.

``extra="forbid"`` on the inbound DTOs is what makes attempts to set
``id`` / ``created_at`` raise a Pydantic ``extra_forbidden`` error — the
global handler in :mod:`app.core.errors` translates those into the
``read_only_field`` envelope (FRD §4).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.core.constants import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, OrderDirection
from app.core.datetime_utils import ensure_utc
from app.services.tasks.constants import (
    DESCRIPTION_MAX_LENGTH,
    PRIORITY_MAX,
    PRIORITY_MIN,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
    Status,
    TaskSortField,
)


def _require_non_blank_title(value: str) -> str:
    """Reject whitespace-only titles at the framework boundary (FRD §2.4).

    Pydantic's ``min_length=1`` only checks the raw string length, so a value
    like ``"   "`` would slip past the DTO and raise a plain ``ValueError``
    inside the domain — which the global handler cannot convert to the
    standard envelope. Tightening the validator here keeps the contract
    surface (422 ``validation_error``) consistent.
    """
    if not value.strip():
        raise ValueError("title must not be blank or whitespace-only")
    return value


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status = Status.NEW
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str) -> str:
        return _require_non_blank_title(value)


class TaskPatch(BaseModel):
    """All fields optional; at least one must be supplied (enforced in service)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)

    @field_validator("title")
    @classmethod
    def _validate_title(cls, value: str | None) -> str | None:
        return _require_non_blank_title(value) if value is not None else None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: Status
    priority: int
    created_at: datetime

    @field_serializer("created_at")
    def _serialize_created_at(self, dt: datetime) -> str:
        # FRD §2.4: emit RFC 3339 with explicit ``Z`` UTC marker. ``ensure_utc``
        # restores tzinfo lost on SQLite roundtrip and converts non-UTC aware
        # datetimes (relevant once Phase 2 swaps in Postgres).
        return ensure_utc(dt).isoformat().replace("+00:00", "Z")


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskListParams(BaseModel):
    """Validated query parameters for ``GET /v1/tasks``.

    Constructed by the ``get_task_query_params`` FastAPI dependency so the
    route handler receives a single typed object instead of five loose
    ``Query(...)`` kwargs. ``extra="forbid"`` keeps unknown query params
    from silently being ignored.
    """

    model_config = ConfigDict(extra="forbid")

    statuses: list[Status] | None = None
    order_by: TaskSortField = TaskSortField.PRIORITY
    order_dir: OrderDirection = OrderDirection.DESC
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(default=0, ge=0)
