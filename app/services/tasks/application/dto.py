"""Request and response DTOs for the tasks feature.

``extra="forbid"`` on the inbound DTOs is what makes attempts to set
``id`` / ``created_at`` raise a Pydantic ``extra_forbidden`` error — the
global handler in :mod:`app.core.errors` translates those into the
``read_only_field`` envelope (FRD §4).
"""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_serializer

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

    Pydantic's ``min_length=1`` only checks raw string length, so ``"   "``
    slips past ``Field(min_length=…)`` and raises a plain ``ValueError`` in the
    domain — which the global handler cannot convert to the standard envelope.
    """
    if not value.strip():
        raise ValueError("title must not be blank or whitespace-only")
    return value


# Reusable Pydantic V2 type alias — bounds + custom validator live with the type,
# not duplicated on every field declaration. ``pattern=r"\S"`` requires at least
# one non-whitespace character; it generates ``"pattern": "\\S"`` in the OpenAPI
# schema so schema-driven fuzzers know ``"\t"`` is not a valid title. The
# ``AfterValidator`` stays as a defence-in-depth check with a clearer error msg.
NonBlankTitle = Annotated[
    str,
    Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH, pattern=r"\S"),
    AfterValidator(_require_non_blank_title),
]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankTitle
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status = Status.NEW
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)


class TaskPatch(BaseModel):
    """All fields optional; at least one must be supplied (enforced in service).

    ``json_schema_extra={"minProperties": 1}`` documents the >= 1-field rule in
    the OpenAPI document so schema-driven fuzzers (schemathesis) treat ``{}`` as
    negative data. Runtime enforcement still lives in the service layer
    (``EmptyUpdateError`` → ``empty_update`` envelope) — this is a documentation
    fix, not a validation change.
    """

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
