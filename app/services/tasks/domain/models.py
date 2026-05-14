"""The ``Task`` domain entity.

The same class doubles as the SQLModel row (``table=True``) and the domain
object — Phase 1 deliberately does not split them (TIS §3.1). The
``title_key`` column is the canonical uniqueness key
(``title.strip().casefold()``); the original ``title`` is preserved verbatim
for display (FRD §2.4).
"""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from app.services.tasks.constants import (
    DESCRIPTION_MAX_LENGTH,
    PRIORITY_MAX,
    PRIORITY_MIN,
    TITLE_MAX_LENGTH,
    TITLE_MIN_LENGTH,
    Status,
)


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
        """Detached copy for event payloads — fresh instance with no session state."""
        return Task.model_validate(self.model_dump())
