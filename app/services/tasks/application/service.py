from typing import Any

from fastapi import BackgroundTasks

from app.core.errors import ValidationError
from app.core.event_bus import EventBus
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import MUTABLE_FIELDS, Task
from app.services.tasks.errors import EmptyUpdateError, InvalidTransitionError
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import COMPLETES_META_KEY, Transition
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

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        status: str | None,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        workflow = self._workflows.get_active().workflow
        resolved = self._resolve_create_status(workflow, status)
        task = self._repo.add(title=title, description=description, status=resolved, priority=priority)
        self._events.publish(TaskCreated(task=task.snapshot()), background_tasks)
        return task

    async def get(self, task_id: int) -> Task:
        return self._repo.get(task_id)

    async def legal_moves(self, task_id: int) -> tuple[Task, list[Transition]]:
        """The task plus the definition-legal transitions out of its state."""
        workflow = self._workflows.get_active().workflow
        task = self._repo.get(task_id)
        return task, workflow.transitions_from(task.status)

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
        status: str | None,
        priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        # The read-workflow → check → write span is await-free: no concurrent
        # PUT /v1/workflow can interleave under the single-threaded loop.
        workflow = self._workflows.get_active().workflow
        # current.status feeds the move check; fetching first also gives 404
        # precedence over any 409/422 the checks below raise.
        current = self._repo.get(task_id)
        target = workflow.default_entry if status is None else status
        self._check_move(workflow, current.status, target)
        previous, updated = self._repo.replace(
            task_id,
            title=title,
            description=description,
            status=target,
            priority=priority,
        )
        self._publish_update_events(previous, updated, workflow, background_tasks)
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
        current = self._repo.get(task_id)  # 404 precedence over any 409/422 below
        workflow: Workflow | None = None
        if "status" in fields:
            # Only status changes consult the definition; the read → check →
            # write span stays await-free (atomicity invariant).
            workflow = self._workflows.get_active().workflow
            self._check_move(workflow, current.status, fields["status"])
        previous, updated = self._repo.patch(task_id, **fields)
        self._publish_update_events(previous, updated, workflow, background_tasks)
        return updated

    async def delete(
        self,
        task_id: int,
        *,
        background_tasks: BackgroundTasks,
    ) -> None:
        snapshot = self._repo.delete(task_id)
        self._events.publish(TaskDeleted(task=snapshot), background_tasks)

    def _resolve_create_status(self, workflow: Workflow, status: str | None) -> str:
        if status is None:
            return workflow.default_entry
        self._require_known(workflow, status)
        entries = workflow.entry_states
        if status not in entries:
            raise InvalidTransitionError(details={"from": None, "to": status, "allowed": entries})
        return status

    def _check_move(self, workflow: Workflow, from_status: str, to_status: str) -> None:
        """Same-state writes are no-moves; anything else needs a defined transition."""
        self._require_known(workflow, to_status)
        if to_status == from_status:
            return
        if workflow.transition_between(from_status, to_status) is None:
            raise InvalidTransitionError(
                details={
                    "from": from_status,
                    "to": to_status,
                    "allowed": sorted(workflow.moves_from(from_status)),
                }
            )

    @staticmethod
    def _require_known(workflow: Workflow, status: str) -> None:
        """A status that is no state at all is a validation error, not a refusal."""
        if status not in workflow.state_names:
            raise ValidationError(
                detail="Unknown workflow state.",
                details={"field": "status", "value": status, "known_states": workflow.state_names},
            )

    def _publish_update_events(
        self,
        previous: Task,
        updated: Task,
        workflow: Workflow | None,
        background_tasks: BackgroundTasks,
    ) -> None:
        """``workflow`` is None only when the write could not have changed status."""
        changed = [field for field in MUTABLE_FIELDS if getattr(updated, field) != getattr(previous, field)]
        if not changed:
            return
        updated_snapshot = updated.snapshot()
        self._events.publish(
            TaskUpdated(task=updated_snapshot, previous=previous, changed_fields=changed),
            background_tasks,
        )
        if "status" not in changed:
            return
        assert workflow is not None  # status changed ⇒ the caller consulted the definition
        self._events.publish(
            TaskStatusChanged(
                task=updated_snapshot,
                from_status=previous.status,
                to_status=updated.status,
            ),
            background_tasks,
        )
        if workflow.state(updated.status).meta.get(COMPLETES_META_KEY):
            self._events.publish(TaskCompleted(task=updated_snapshot), background_tasks)
