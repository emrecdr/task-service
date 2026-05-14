"""Use-case orchestration for the tasks feature.

Owns the event-firing rules from FRD §5.1:

- ``TaskCreated`` after a successful ``add``.
- ``TaskUpdated`` only when at least one mutable field actually changed.
- ``TaskStatusChanged`` only when ``status`` was among the changed fields.
- ``TaskCompleted`` only when ``status`` transitioned to ``completed``.
- ``TaskDeleted`` after a successful ``delete``, carrying the snapshot.

The previous-state snapshot is taken via ``model_validate(model_dump())`` so
the in-place patch can mutate the row without losing the pre-change values.
"""

from typing import Any

from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status
from app.services.tasks.errors import EmptyUpdateError
from app.services.tasks.interfaces import MUTABLE_FIELDS, Sort, TaskRepositoryInterface


class TaskService:
    def __init__(self, *, repo: TaskRepositoryInterface, events: EventBus) -> None:
        self._repo = repo
        self._events = events

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        task = self._repo.add(title=title, description=description, status=status, priority=priority)
        await self._events.publish(TaskCreated(task=task), background_tasks)
        return task

    def get(self, task_id: int) -> Task:
        return self._repo.get(task_id)

    def list(
        self,
        *,
        statuses: list[Status] | None,
        sort: Sort,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        return self._repo.list(statuses=statuses, sort=sort, limit=limit, offset=offset)

    async def replace(
        self,
        task_id: int,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        previous = self._snapshot(self._repo.get(task_id))
        updated = self._repo.replace(
            task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
        )
        await self._publish_update_events(previous, updated, background_tasks)
        return updated

    async def patch(
        self,
        task_id: int,
        *,
        fields: dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> Task:
        if not fields:
            raise EmptyUpdateError()
        previous = self._snapshot(self._repo.get(task_id))
        updated = self._repo.patch(task_id, **fields)
        await self._publish_update_events(previous, updated, background_tasks)
        return updated

    async def delete(
        self,
        task_id: int,
        *,
        background_tasks: BackgroundTasks,
    ) -> Task:
        snapshot = self._repo.delete(task_id)
        await self._events.publish(TaskDeleted(task=snapshot), background_tasks)
        return snapshot

    @staticmethod
    def _snapshot(task: Task) -> Task:
        return Task.model_validate(task.model_dump())

    async def _publish_update_events(
        self,
        previous: Task,
        updated: Task,
        background_tasks: BackgroundTasks,
    ) -> None:
        changed = [field for field in MUTABLE_FIELDS if getattr(updated, field) != getattr(previous, field)]
        if not changed:
            return
        await self._events.publish(
            TaskUpdated(task=updated, previous=previous, changed_fields=changed),
            background_tasks,
        )
        if "status" in changed:
            await self._events.publish(
                TaskStatusChanged(
                    task=updated,
                    from_status=previous.status,
                    to_status=updated.status,
                ),
                background_tasks,
            )
            if updated.status is Status.COMPLETED:
                await self._events.publish(TaskCompleted(task=updated), background_tasks)
