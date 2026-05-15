"""FastAPI dependency providers for the tasks feature.

Composes the repository (concrete adapter) and the application service
from the cross-cutting primitives in :mod:`app.core.dependencies`.
"""

from typing import Annotated

from fastapi import Depends, Query
from sqlmodel import Session

from app.core.constants import DEFAULT_LIST_LIMIT, MAX_LIST_LIMIT, OrderDirection
from app.core.dependencies import get_event_bus, get_session
from app.core.event_bus import EventBus
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.application.service import TaskService
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.tasks.interfaces import TaskRepositoryInterface

SessionDep = Annotated[Session, Depends(get_session)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


def get_repository(session: SessionDep) -> TaskRepositoryInterface:
    return SQLModelTaskRepository(session)


RepositoryDep = Annotated[TaskRepositoryInterface, Depends(get_repository)]


def get_task_service(repo: RepositoryDep, events: EventBusDep) -> TaskService:
    return TaskService(repo=repo, events=events)


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]


def get_task_query_params(
    statuses: Annotated[
        list[Status] | None,
        Query(alias="status", description="Filter by status. Repeat the param for multiple values."),
    ] = None,
    order_by: Annotated[
        TaskSortField,
        Query(description="Field to order results by."),
    ] = TaskSortField.PRIORITY,
    order_dir: Annotated[
        OrderDirection,
        Query(description="Sort direction."),
    ] = OrderDirection.DESC,
    limit: Annotated[int, Query(ge=1, le=MAX_LIST_LIMIT)] = DEFAULT_LIST_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TaskListParams:
    """Bind ``GET /v1/tasks`` query parameters into a single validated DTO."""
    return TaskListParams(
        statuses=statuses,
        order_by=order_by,
        order_dir=order_dir,
        limit=limit,
        offset=offset,
    )


TaskQueryParamsDep = Annotated[TaskListParams, Depends(get_task_query_params)]
