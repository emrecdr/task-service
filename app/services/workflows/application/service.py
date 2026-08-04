from collections.abc import Sequence
from typing import Any

from app.core.event_bus import Event
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
    ) -> None:
        self._repo = repo
        self._usage = usage

    async def get_active(self) -> StoredWorkflow:
        return await self._repo.get_active()

    async def replace_active(self, *, document: dict[str, Any]) -> StoredWorkflow:
        """Validate, strand-check, and store a new definition version.

        Validation is pure (fail fast without the lock); the guard then makes the
        usage-count → check → commit span atomic against concurrent task writes —
        the advisory lock is held from here until ``replace_active`` commits. The
        ``WorkflowUpdated`` event is staged in that same commit (the repo assigns the
        version and invokes this closure with it)."""
        workflow = workflow_from_document(document)
        await self._repo.acquire_workflow_guard()
        known = set(workflow.state_names)
        counts = await self._usage.count_by_status()
        stranded = {state: count for state, count in counts.items() if state not in known}
        if stranded:
            raise WorkflowStatesInUseError(details={"states": stranded})

        def make_events(version: int) -> Sequence[Event]:
            return [WorkflowUpdated(version=version, states=workflow.state_names)]

        return await self._repo.replace_active(workflow, make_events=make_events)
