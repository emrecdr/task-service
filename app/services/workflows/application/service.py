from typing import Any

from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.events import WorkflowUpdated
from app.services.workflows.errors import WorkflowStatesInUseError
from app.services.workflows.interfaces import StoredWorkflow, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_from_document


class WorkflowService:
    def __init__(
        self,
        *,
        repo: WorkflowRepositoryInterface,
        tasks: TaskRepositoryInterface,
        events: EventBus,
    ) -> None:
        self._repo = repo
        self._tasks = tasks
        self._events = events

    async def get_active(self) -> StoredWorkflow:
        return self._repo.get_active()

    async def replace_active(
        self,
        *,
        document: dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> StoredWorkflow:
        """Validate, strand-check, and store a new definition version.

        The usage-count → check → commit span is await-free, so no concurrent
        task write can interleave under the single-threaded event loop.
        """
        workflow = workflow_from_document(document)
        known = set(workflow.state_names)
        stranded = {state: count for state, count in self._tasks.count_by_status().items() if state not in known}
        if stranded:
            raise WorkflowStatesInUseError(details={"states": stranded})
        stored = self._repo.replace_active(workflow)
        self._events.publish(
            WorkflowUpdated(version=stored.version, states=workflow.state_names),
            background_tasks,
        )
        return stored
