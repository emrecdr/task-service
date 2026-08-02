import uuid
from typing import Any

from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import EmptyUpdateError
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.engine import WorkflowEngine
from app.services.workflows.domain.models import Transition
from app.services.workflows.interfaces import WorkflowRepositoryInterface


class TaskService:
    def __init__(
        self,
        *,
        repo: TaskRepositoryInterface,
        workflows: WorkflowRepositoryInterface,
        events: EventBus,
    ) -> None:
        self._repo = repo
        self._workflows = workflows
        self._events = events

    async def _engine(self) -> WorkflowEngine:
        """Wrap the active definition, read fresh. Read-only callers (``legal_moves``) use
        this directly; every mutator enters through ``_guarded_engine`` instead."""
        return WorkflowEngine((await self._workflows.get_active()).workflow)

    async def _guarded_engine(self) -> WorkflowEngine:
        """Acquire the workflow advisory guard, then read the active definition under it.
        The single seam every status-changing path enters through, so the read-check-write
        span stays atomic against a concurrent ``PUT /v1/workflow`` even over the async pool.
        """
        await self._workflows.acquire_workflow_guard()
        return await self._engine()

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        status: str | None,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        engine = await self._guarded_engine()
        resolved = engine.resolve_entry(status)
        task = await self._repo.add(title=title, description=description, status=resolved, priority=priority)
        self._events.publish(TaskCreated(task=task.snapshot()), background_tasks)
        return task

    async def get(self, task_id: uuid.UUID) -> Task:
        return await self._repo.get(task_id)

    async def legal_moves(self, task_id: uuid.UUID) -> tuple[Task, list[Transition]]:
        """The task plus the definition-legal transitions out of its state (read-only — no guard)."""
        engine = await self._engine()
        task = await self._repo.get(task_id)
        return task, engine.legal_moves(task.status)

    async def list(self, *, params: TaskListParams) -> tuple[list[Task], int]:
        return await self._repo.list(
            statuses=params.statuses,
            order_by=params.order_by,
            order_dir=params.order_dir,
            limit=params.limit,
            offset=params.offset,
        )

    async def replace(
        self,
        task_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        status: str | None,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        engine = await self._guarded_engine()
        # Fetching current also gives 404 precedence over any 409/422 the checks raise.
        current = await self._repo.get(task_id)
        target = engine.default_entry if status is None else status
        engine.check_move(current.status, target)
        previous, updated = await self._repo.replace(
            task_id,
            title=title,
            description=description,
            status=target,
            priority=priority,
        )
        self._publish_update_events(previous, updated, engine, background_tasks)
        return updated

    async def patch(
        self,
        task_id: uuid.UUID,
        *,
        fields: dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> Task:
        if not fields:
            raise EmptyUpdateError()
        # A status change consults the workflow, so it takes the guard + reads the definition
        # up front; a non-status patch skips both. ``engine is None`` ⇒ status cannot change.
        engine = await self._guarded_engine() if "status" in fields else None
        current = await self._repo.get(task_id)  # 404 precedence over any 409/422 below
        if engine is not None:
            engine.check_move(current.status, fields["status"])
        previous, updated = await self._repo.patch(task_id, **fields)
        self._publish_update_events(previous, updated, engine, background_tasks)
        return updated

    async def delete(
        self,
        task_id: uuid.UUID,
        *,
        background_tasks: BackgroundTasks,
    ) -> None:
        snapshot = await self._repo.delete(task_id)
        self._events.publish(TaskDeleted(task=snapshot), background_tasks)

    def _publish_update_events(
        self,
        previous: Task,
        updated: Task,
        engine: WorkflowEngine | None,
        background_tasks: BackgroundTasks,
    ) -> None:
        """``engine`` is None only when the write could not have changed status."""
        changed = updated.changed_fields(previous)
        if not changed:
            return
        updated_snapshot = updated.snapshot()
        self._events.publish(
            TaskUpdated(task=updated_snapshot, previous=previous, changed_fields=changed),
            background_tasks,
        )
        if "status" not in changed:
            return
        assert engine is not None  # status changed ⇒ the caller consulted the definition
        self._events.publish(
            TaskStatusChanged(
                task=updated_snapshot,
                from_status=previous.status,
                to_status=updated.status,
            ),
            background_tasks,
        )
        if engine.completes(updated.status):
            self._events.publish(TaskCompleted(task=updated_snapshot), background_tasks)
