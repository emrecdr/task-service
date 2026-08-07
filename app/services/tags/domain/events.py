import uuid
from typing import Final

from app.core.event_bus import Event


class TaskTagsChanged(Event):
    """A create or update left the task's tag set different from what it was.

    Independent of ``TaskUpdated``: a tags-only change fires this alone, because no ``Task``
    column moved. Carries ``task_id`` rather than a ``Task`` snapshot — tags live in their own
    tables, so a detached ``Task`` has no attribute to populate, and adding one purely to fill
    an event payload would push tag state into the tasks feature (FRD §5.1).
    """

    task_id: uuid.UUID
    tags: list[str]
    added: list[str]
    removed: list[str]


class TagDeleted(Event):
    tag_id: uuid.UUID
    name: str


# Listener registration enumerates these; keep in lock-step with the services that emit them.
TAG_EVENT_TYPES: Final[tuple[type[Event], ...]] = (
    TaskTagsChanged,
    TagDeleted,
)
