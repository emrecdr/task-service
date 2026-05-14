"""Request and response DTOs for the tasks feature.

``extra="forbid"`` on the inbound DTOs is what makes attempts to set
``id`` / ``created_at`` raise a Pydantic ``extra_forbidden`` error — the
global handler in :mod:`app.core.errors` translates those into the
``read_only_field`` envelope (FRD §4).
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.services.tasks.enums import Status


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Status = Status.NEW
    priority: int = Field(ge=1, le=5)


class TaskPatch(BaseModel):
    """All fields optional; at least one must be supplied (enforced in service)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


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
        # SQLite strips tzinfo on roundtrip; the column is always written
        # with datetime.now(UTC), so attaching UTC on the way out preserves
        # the FRD §2.4 invariant (RFC 3339 with explicit ``Z`` suffix).
        aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        return aware.isoformat().replace("+00:00", "Z")


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int
