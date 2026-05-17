"""Use-case orchestration for the tasks feature; owns event-firing rules."""

from typing import Any

from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.constants import Status
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import MUTABLE_FIELDS, Task
from app.services.tasks.errors import EmptyUpdateError
from app.services.tasks.interfaces import TaskRepositoryInterface


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
        self._events.publish(TaskCreated(task=task), background_tasks)
        return task

    async def get(self, task_id: int) -> Task:
        return self._repo.get(task_id)

    async def list(self, *, params: TaskListParams) -> tuple[list[Task], int]:
        return self._repo.list(
            statuses=params.statuses,
            order_by=params.order_by,
            order_dir=params.order_dir,
            limit=params.limit,
            offset=params.offset,
        )

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
        previous, updated = self._repo.replace(
            task_id,
            title=title,
            description=description,
            status=status,
            priority=priority,
        )
        self._publish_update_events(previous, updated, background_tasks)
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
        previous, updated = self._repo.patch(task_id, **fields)
        self._publish_update_events(previous, updated, background_tasks)
        return updated

    async def delete(
        self,
        task_id: int,
        *,
        background_tasks: BackgroundTasks,
    ) -> None:
        snapshot = self._repo.delete(task_id)
        self._events.publish(TaskDeleted(task=snapshot), background_tasks)

    def _publish_update_events(
        self,
        previous: Task,
        updated: Task,
        background_tasks: BackgroundTasks,
    ) -> None:
        changed = [field for field in MUTABLE_FIELDS if getattr(updated, field) != getattr(previous, field)]
        if not changed:
            return
        self._events.publish(
            TaskUpdated(task=updated, previous=previous, changed_fields=changed),
            background_tasks,
        )
        if "status" in changed:
            self._events.publish(
                TaskStatusChanged(
                    task=updated,
                    from_status=previous.status,
                    to_status=updated.status,
                ),
                background_tasks,
            )
            if updated.status is Status.COMPLETED:
                self._events.publish(TaskCompleted(task=updated), background_tasks)
