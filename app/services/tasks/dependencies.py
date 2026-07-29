from typing import Annotated

from fastapi import Depends, Query

from app.core.dependencies import EventBusDep, SessionDep
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.application.service import TaskService
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository


def get_task_service(session: SessionDep, events: EventBusDep) -> TaskService:
    # Both repositories share the request's single session — the atomicity of
    # the read-workflow → check-move → write span depends on it.
    return TaskService(
        repo=SQLModelTaskRepository(session),
        workflows=SQLModelWorkflowRepository(session),
        events=events,
    )


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]

TaskQueryParamsDep = Annotated[TaskListParams, Query()]
