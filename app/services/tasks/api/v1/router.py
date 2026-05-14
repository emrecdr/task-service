"""HTTP routes for the tasks feature — six endpoints under ``/tasks``.

Mounted by :mod:`app.main` under ``settings.api_v1_prefix`` (default ``/v1``).
DTO validation (incl. ``extra="forbid"`` for read-only-field rejection)
happens at the framework boundary; the service layer takes the unpacked
fields as kwargs to stay adapter-agnostic.

Handlers return the raw :class:`Task` row; ``response_model=TaskResponse``
on the decorator drives both the OpenAPI schema and the actual conversion
(via ``TaskResponse.model_config.from_attributes=True``).
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.services.tasks.application.dto import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskResponse,
)
from app.services.tasks.application.service import TaskService
from app.services.tasks.dependencies import get_task_service
from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status
from app.services.tasks.interfaces import Sort

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    service: TaskService = Depends(get_task_service),
) -> Task:
    return await service.create(**body.model_dump(), background_tasks=background_tasks)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    service: TaskService = Depends(get_task_service),
    statuses: list[Status] | None = Query(default=None, alias="status"),
    sort: Sort = "priority_desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    items, total = service.list(statuses=statuses, sort=sort, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
) -> Task:
    return service.get(task_id)


@router.put("/{task_id}", response_model=TaskResponse)
async def replace_task(
    task_id: int,
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    service: TaskService = Depends(get_task_service),
) -> Task:
    return await service.replace(task_id, **body.model_dump(), background_tasks=background_tasks)


@router.patch("/{task_id}", response_model=TaskResponse)
async def patch_task(
    task_id: int,
    body: TaskPatch,
    background_tasks: BackgroundTasks,
    service: TaskService = Depends(get_task_service),
) -> Task:
    return await service.patch(
        task_id,
        fields=body.model_dump(exclude_unset=True),
        background_tasks=background_tasks,
    )


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    background_tasks: BackgroundTasks,
    service: TaskService = Depends(get_task_service),
) -> None:
    await service.delete(task_id, background_tasks=background_tasks)
