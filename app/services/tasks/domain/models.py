"""The ``Task`` domain entity (doubles as SQLModel row)."""

from datetime import UTC, datetime
from typing import Any, Final

from sqlmodel import Field, SQLModel

from app.services.tasks.constants import (
    DESCRIPTION_MAX_LENGTH,
    PRIORITY_MAX,
    PRIORITY_MIN,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
    Status,
)

# Fields the domain accepts for replace/patch mutation and the service uses for change-detection.
MUTABLE_FIELDS: Final[frozenset[str]] = frozenset({"title", "description", "status", "priority"})


class Task(SQLModel, table=True):
    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(min_length=TITLE_MIN_LENGTH, max_length=TITLE_MAX_LENGTH)
    title_key: str = Field(index=True, unique=True, max_length=TITLE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)
    status: Status = Field(default=Status.NEW)
    priority: int = Field(ge=PRIORITY_MIN, le=PRIORITY_MAX)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    @staticmethod
    def normalize_title(title: str) -> str:
        """Return the canonical uniqueness key for a title."""
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
        status: Status,
        priority: int,
    ) -> "Task":
        """Build a Task from caller input, applying normalisation invariants."""
        cleaned_title, title_key = cls.clean_title(title)
        return cls(
            title=cleaned_title,
            title_key=title_key,
            description=description,
            status=status,
            priority=priority,
        )

    def snapshot(self) -> "Task":
        """Detached, revalidated copy for event payloads."""
        return Task.model_validate(self.model_dump())

    def apply_replace(
        self,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> None:
        """Overwrite every mutable field; ``title_key`` is recomputed from ``title``."""
        self.title, self.title_key = Task.clean_title(title)
        self.description = description
        self.status = status
        self.priority = priority

    def apply_patch(self, fields: dict[str, Any]) -> None:
        """Apply a partial update; raise ``ValueError`` for any non-mutable key."""
        unknown = set(fields) - MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unknown patch fields: {sorted(unknown)}")
        if "title" in fields:
            self.title, self.title_key = Task.clean_title(fields["title"])
        for field, value in fields.items():
            if field == "title":
                continue
            setattr(self, field, value)
