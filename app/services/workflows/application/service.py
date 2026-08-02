from typing import Any

from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.workflows.domain.events import WorkflowUpdated
from app.services.workflows.errors import WorkflowStatesInUseError
from app.services.workflows.interfaces import StatusUsagePort, StoredWorkflow, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_from_document


class WorkflowService:
    def __init__(
        self,
        *,
        repo: WorkflowRepositoryInterface,
        usage: StatusUsagePort,
        events: EventBus,
    ) -> None:
        self._repo = repo
        self._usage = usage
        self._events = events

    async def get_active(self) -> StoredWorkflow:
        return await self._repo.get_active()

    async def replace_active(
        self,
        *,
        document: dict[str, Any],
        background_tasks: BackgroundTasks,
    ) -> StoredWorkflow:
        """Validate, strand-check, and store a new definition version.

        Validation is pure (fail fast without the lock); the guard then makes the
        usage-count → check → commit span atomic against concurrent task writes —
        the advisory lock is held from here until ``replace_active`` commits.
        """
        workflow = workflow_from_document(document)
        await self._repo.acquire_workflow_guard()
        known = set(workflow.state_names)
        counts = await self._usage.count_by_status()
        stranded = {state: count for state, count in counts.items() if state not in known}
        if stranded:
            raise WorkflowStatesInUseError(details={"states": stranded})
        stored = await self._repo.replace_active(workflow)
        self._events.publish(
            WorkflowUpdated(version=stored.version, states=workflow.state_names),
            background_tasks,
        )
        return stored
