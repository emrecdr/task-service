import uuid
from datetime import UTC, datetime
from typing import Any, Final, Self

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.services.tasks.constants import (
    DESCRIPTION_MAX_LENGTH,
    PRIORITY_MAX,
    PRIORITY_MIN,
    TITLE_KEY_CONSTRAINT,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
)

# Canonical order is the field-ordering contract for ``TaskUpdated.changed_fields`` event payloads.
MUTABLE_FIELDS: Final[tuple[str, ...]] = ("title", "description", "status", "priority")


class Task(SQLModel, table=True):
    __tablename__ = "tasks"  # pyright: ignore[reportAssignmentType]
    # Named explicitly so duplicate detection matches the constraint name via asyncpg,
    # not a dialect-specific error-message substring.
    __table_args__ = (UniqueConstraint("title_key", name=TITLE_KEY_CONSTRAINT),)

    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    title: str = Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH)
    title_key: str = Field(max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: str
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        # timestamptz — preserve tz on Postgres (sa_column, so default stays Python-side).
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    @staticmethod
    def normalize_title(title: str) -> str:
        return title.strip().casefold()

    @classmethod
    def clean_title(cls, title: str) -> tuple[str, str]:
        """Return ``(stripped_title, title_key)``; raise ``ValueError`` if empty."""
        title_key = cls.normalize_title(title)
        if not title_key:
            raise ValueError("title must not be empty")
        return title.strip(), title_key

    @classmethod
    def from_input(
        cls,
        *,
        title: str,
        description: str | None,
        status: str,
        priority: int,
    ) -> Self:
        """Build a Task from caller input, applying normalisation invariants."""
        cleaned_title, title_key = cls.clean_title(title)
        return cls(
            title=cleaned_title,
            title_key=title_key,
            description=description,
            status=status,
            priority=priority,
        )

    def snapshot(self) -> Self:
        """Detached, revalidated copy for event payloads."""
        return type(self).model_validate(self.model_dump())

    def changed_fields(self, previous: Self) -> list[str]:
        """Mutable fields whose value differs from ``previous``, in canonical order.

        The single source of truth for "did this write change anything" — the
        repository gates its commit on it and the service gates event fan-out on it.
        """
        return [field for field in MUTABLE_FIELDS if getattr(self, field) != getattr(previous, field)]

    def apply_replace(
        self,
        *,
        title: str,
        description: str | None,
        status: str,
        priority: int,
    ) -> None:
        """Overwrite every mutable field; ``title_key`` is recomputed from ``title``."""
        self.title, self.title_key = Task.clean_title(title)
        self.description = description
        self.status = status
        self.priority = priority

    def apply_patch(self, fields: dict[str, Any]) -> None:
        """Apply a partial update; raise ``ValueError`` for any non-mutable key."""
        unknown = set(fields).difference(MUTABLE_FIELDS)
        if unknown:
            raise ValueError(f"unknown patch fields: {sorted(unknown)}")
        for field, value in fields.items():
            if field == "title":
                self.title, self.title_key = Task.clean_title(value)
            else:
                setattr(self, field, value)
