from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.application.service import WorkflowService
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository
from app.services.workflows.interfaces import StatusUsagePort


class _TaskStatusUsage(StatusUsagePort):
    """Adapts the tasks repository to the workflow-owned ``StatusUsagePort`` so the
    workflows feature depends on a narrow port, never the full task-repo interface.
    Lives in the DI seam because only ``dependencies.py`` may bridge two features."""

    def __init__(self, tasks: TaskRepositoryInterface) -> None:
        self._tasks = tasks

    async def count_by_status(self) -> dict[str, int]:
        return await self._tasks.count_by_status()


def get_workflow_service(session: SessionDep) -> WorkflowService:
    # Both repositories share the request's single session — the atomicity of the strand
    # guard's count → check → commit span (and the staged WorkflowUpdated) depends on it.
    return WorkflowService(
        repo=SQLModelWorkflowRepository(session),
        usage=_TaskStatusUsage(SQLModelTaskRepository(session)),
    )


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
