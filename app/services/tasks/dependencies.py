from typing import Annotated

from fastapi import Depends, Query

from app.core.dependencies import EventBusDep, SessionDep
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.application.service import TaskService
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository


def get_task_service(session: SessionDep, events: EventBusDep) -> TaskService:
    return TaskService(repo=SQLModelTaskRepository(session), events=events)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]

TaskQueryParamsDep = Annotated[TaskListParams, Query()]
