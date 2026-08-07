import uuid
from typing import Annotated, Any, Final, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.core.constants import DEFAULT_LIST_LIMIT, INT64_MAX, MAX_LIST_LIMIT, OrderDirection
from app.core.datetime_utils import IsoUtcDatetime
from app.services.tags.constants import MAX_TAGS_PER_TASK, NAME_MAX_LENGTH, NAME_MIN_LENGTH, TagMatchOp
from app.services.tasks.constants import (
    DESCRIPTION_MAX_LENGTH,
    PRIORITY_MAX,
    PRIORITY_MIN,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
    TaskSortField,
)


def _reject_nul(value: str) -> str:
    # Postgres text cannot hold a NUL (0x00) byte — asyncpg raises CharacterNotInRepertoireError
    # mid-query — so reject it at the boundary as a 422 rather than letting it 500. Applies to
    # every inbound string that reaches a column or a WHERE clause (title/description/status/filter).
    if "\x00" in value:
        raise ValueError("must not contain a NUL (0x00) character")
    return value


# A ``str`` that additionally rejects the NUL byte Postgres can't store.
NulSafeStr = Annotated[str, AfterValidator(_reject_nul)]

NonBlankTitle = Annotated[
    NulSafeStr,
    Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH, pattern=r"\S"),
]

# ``| None`` on these inbound fields means "omittable", never "nullable" — the
# underlying columns are NOT NULL, so an explicit JSON null must reject as 422.
# Omission is the ONLY spelling of "use the default" (One Obvious Way).
_NON_NULLABLE_PATCH_FIELDS: Final[tuple[str, ...]] = ("title", "status", "priority")
_NON_NULLABLE_CREATE_FIELDS: Final[tuple[str, ...]] = ("status",)


def _reject_explicit_nulls(model: BaseModel, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"{field} must not be null")


TagName = Annotated[NulSafeStr, Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)]


class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankTitle
    description: NulSafeStr | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    # None = "use the active workflow's default entry state"; validated by the service.
    status: NulSafeStr | None = None
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)
    tags: list[TagName] | None = Field(
        default=None, max_length=MAX_TAGS_PER_TASK, description="Tag names; unknown names are created."
    )

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        _reject_explicit_nulls(self, _NON_NULLABLE_CREATE_FIELDS)
        return self


class TaskPatch(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"minProperties": 1},
    )

    title: NonBlankTitle | None = None
    description: NulSafeStr | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: NulSafeStr | None = None
    priority: int | None = Field(default=None, ge=PRIORITY_MIN, le=PRIORITY_MAX)
    tags: list[TagName] | None = Field(
        default=None, max_length=MAX_TAGS_PER_TASK, description="Tag names; unknown names are created."
    )

    @model_validator(mode="after")
    def _reject_explicit_null(self) -> Self:
        _reject_explicit_nulls(self, _NON_NULLABLE_PATCH_FIELDS)
        return self


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    priority: int
    created_at: IsoUtcDatetime
    # Not a Task column: the router fills this from TagRepository.names_for_tasks.
    tags: list[str] = Field(default_factory=list)


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int


class TransitionOption(BaseModel):
    """A definition-legal move out of the task's current state — a UI button.

    ``meta`` passes through uninterpreted (colors, roles, ...)."""

    name: str
    to: str
    meta: dict[str, Any]


class TaskTransitionsResponse(BaseModel):
    task_id: uuid.UUID
    status: str
    transitions: list[TransitionOption]


class TaskListParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statuses: list[NulSafeStr] | None = Field(
        default=None,
        alias="status",
        description="Filter by status. Repeat the param for multiple values.",
    )
    tags: list[NulSafeStr] | None = Field(
        default=None,
        alias="tag",
        description="Filter by tag name. Repeat the param for multiple values; see ``op``.",
    )
    op: TagMatchOp = Field(
        default=TagMatchOp.AND,
        description="How repeated ``tag`` values combine: ``and`` (carry every tag) or ``or`` "
        "(carry any). Applies to ``tag`` only — a task holds one status, so an AND across "
        "statuses could never match.",
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
    # asyncpg binds OFFSET as a signed int64; values beyond it overflow the driver.
    offset: int = Field(default=0, ge=0, le=INT64_MAX)
