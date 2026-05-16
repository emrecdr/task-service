"""Request and response DTOs for the tasks feature."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_serializer

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

NonBlankTitle = Annotated[
    str,
    Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH, pattern=r"\S"),
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankTitle
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status = Status.NEW
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)


class TaskPatch(BaseModel):
    """All fields optional; empty payload raises ``EmptyUpdateError`` at the service."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"minProperties": 1},
    )

    title: NonBlankTitle | None = None
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)


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
        return ensure_utc(dt).isoformat().replace("+00:00", "Z")


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class TaskListParams(BaseModel):
    """Validated query parameters for ``GET /v1/tasks``."""

    model_config = ConfigDict(extra="forbid")

    statuses: list[Status] | None = Field(
        default=None,
        alias="status",
        description="Filter by status. Repeat the param for multiple values.",
    )
    order_by: TaskSortField = Field(
        default=TaskSortField.PRIORITY,
        description="Field to order results by.",
    )
    order_dir: OrderDirection = Field(
        default=OrderDirection.DESC,
        description="Sort direction.",
    )
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)
    offset: int = Field(default=0, ge=0)
