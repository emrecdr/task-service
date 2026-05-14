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


def get_repository(session: Session = Depends(get_session)) -> TaskRepositoryInterface:
    return SQLModelTaskRepository(session)


def get_task_service(
    repo: TaskRepositoryInterface = Depends(get_repository),
    events: EventBus = Depends(get_event_bus),
) -> TaskService:
    return TaskService(repo=repo, events=events)


def get_task_query_params(
    statuses: list[Status] | None = Query(
        default=None,
        alias="status",
        description="Filter by status. Repeat the param for multiple values.",
    ),
    order_by: TaskSortField = Query(
        default=TaskSortField.PRIORITY,
        description="Field to order results by.",
    ),
    order_dir: OrderDirection = Query(
        default=OrderDirection.DESC,
        description="Sort direction.",
    ),
    limit: int = Query(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    offset: int = Query(default=0, ge=0),
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
