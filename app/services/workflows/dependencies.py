from typing import Annotated

from fastapi import Depends

from app.core.dependencies import EventBusDep, SessionDep
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.workflows.application.service import WorkflowService
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository


def get_workflow_service(session: SessionDep, events: EventBusDep) -> WorkflowService:
    # Both repositories share the request's single session — the atomicity of
    # the strand guard's count → check → commit span depends on it.
    return WorkflowService(
        repo=SQLModelWorkflowRepository(session),
        tasks=SQLModelTaskRepository(session),
        events=events,
    )


WorkflowServiceDep = Annotated[WorkflowService, Depends(get_workflow_service)]
