import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.event_bus import Event
from app.services.tags.domain.models import Tag


class TagRepositoryInterface(ABC):
    """Persistence port for the tag vocabulary and the task↔tag join (TIS §5.1).

    The tasks feature depends on this ABC, never on a concrete adapter. Every method is
    shaped by how it is consumed rather than by the entity: the two read paths are batch
    because the alternative makes ``GET /v1/tasks`` N+1.
    """

    @abstractmethod
    async def resolve(self, names: Sequence[str]) -> dict[str, uuid.UUID]:
        """Map submitted names to tag IDs, creating any that do not exist yet.

        Keyed by ``name_key``, so the caller's casing is irrelevant and duplicates within one
        request collapse. Creation happens in the caller's transaction — a tag exists because
        a task wears it (FRD §2.7).
        """

    @abstractmethod
    async def set_for_task(self, task_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]) -> None:
        """Replace a task's tag set wholesale. Replacement, never merge (FRD §2.7)."""

    @abstractmethod
    async def names_for_tasks(self, task_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        """Tag names per task, sorted, for list and detail responses.

        Batch by design: a per-task lookup would issue one query per row returned.
        """

    @abstractmethod
    async def task_ids_matching(self, name_keys: Sequence[str], *, match_all: bool) -> set[uuid.UUID]:
        """Task IDs carrying the named tags — every one when ``match_all``, else any (``?op=``)."""

    @abstractmethod
    async def list_with_counts(self) -> list[tuple[Tag, int]]:
        """The whole vocabulary with per-tag task counts. Unpaginated (FRD §3.2)."""

    @abstractmethod
    async def get(self, tag_id: uuid.UUID) -> Tag:
        """Raise ``TagNotFoundError`` when absent — absence is a domain fact, not a sentinel."""

    @abstractmethod
    async def task_count(self, tag_id: uuid.UUID) -> int:
        """How many tasks currently hold this tag — the in-use guard's evidence."""

    @abstractmethod
    async def remove(self, tag: Tag, *, events: Sequence[Event]) -> None:
        """Delete the tag, staging ``events`` into the outbox in the same transaction."""
