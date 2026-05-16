"""Domain events for the tasks feature.

``TaskCompleted`` is a convenience event derived from ``TaskStatusChanged``
for listeners that only care about the completion transition.
"""

from app.core.event_bus import Event
from app.services.tasks.constants import Status
from app.services.tasks.domain.models import Task


class TaskCreated(Event):
    task: Task


class TaskUpdated(Event):
    task: Task
    previous: Task
    changed_fields: list[str]


class TaskStatusChanged(Event):
    task: Task
    from_status: Status
    to_status: Status


class TaskCompleted(Event):
    task: Task


class TaskDeleted(Event):
    task: Task
