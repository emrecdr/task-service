import uuid
from datetime import UTC, datetime
from typing import Self

from sqlalchemy import Column, DateTime, ForeignKey, Index, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.services.tags.constants import NAME_KEY_CONSTRAINT, NAME_MAX_LENGTH, NAME_MIN_LENGTH


class Tag(SQLModel, table=True):
    """A label a task can carry. ``name`` is display, ``name_key`` is identity."""

    __tablename__ = "tags"  # pyright: ignore[reportAssignmentType]
    # Named explicitly so duplicate detection matches the constraint name via asyncpg,
    # not a dialect-specific error-message substring.
    __table_args__ = (UniqueConstraint("name_key", name=NAME_KEY_CONSTRAINT),)

    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    name: str = Field(min_length=NAME_MIN_LENGTH, max_length=NAME_MAX_LENGTH)
    name_key: str = Field(max_length=NAME_MAX_LENGTH)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        # timestamptz — preserve tz on Postgres (sa_column, so default stays Python-side).
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    @staticmethod
    def normalize_name(name: str) -> str:
        """The comparison key: identical rule to ``Task.normalize_title`` (FRD §2.5)."""
        return name.strip().casefold()

    @classmethod
    def clean_name(cls, name: str) -> tuple[str, str]:
        """Return ``(stripped_name, name_key)``; raise ``ValueError`` if empty."""
        stripped = name.strip()
        if not stripped:
            raise ValueError("Tag name must not be blank.")
        return stripped, cls.normalize_name(stripped)

    @classmethod
    def from_name(cls, name: str) -> Self:
        stripped, name_key = cls.clean_name(name)
        return cls(name=stripped, name_key=name_key)


class TaskTag(SQLModel, table=True):
    """The task↔tag join. Both sides cascade: deleting either end drops the link, so a
    deleted task cannot leave orphaned rows behind and the tag-in-use count stays honest."""

    __tablename__ = "task_tags"  # pyright: ignore[reportAssignmentType]
    # The composite PK indexes ``task_id`` as its leading column, which covers
    # ``names_for_tasks``. Nothing covers ``tag_id`` on its own, and both the ``?tag=`` filter
    # and the delete guard's count filter on exactly that — so they would scan the whole join
    # without this.
    __table_args__ = (Index("ix_task_tags_tag_id", "tag_id"),)

    task_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True),
    )
    tag_id: uuid.UUID = Field(
        sa_column=Column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    )
