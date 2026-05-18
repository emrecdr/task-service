from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Path, status

from app.core.constants import INT64_MAX
from app.core.openapi_responses import (
    CONFLICT_RESPONSE,
    NOT_FOUND_RESPONSE,
    VALIDATION_RESPONSE,
)
from app.services.tasks.application.dto import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskResponse,
)
from app.services.tasks.dependencies import TaskQueryParamsDep, TaskServiceDep
from app.services.tasks.domain.models import Task

TaskIdPath = Annotated[int, Path(le=INT64_MAX, json_schema_extra={"format": "int64"})]

router = APIRouter(prefix="/tasks", tags=["tasks"])

# ======================================================= #
# ----- Task Create Route ----- #


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    responses={
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    service: TaskServiceDep,
) -> Task:
    return await service.create(**body.model_dump(), background_tasks=background_tasks)


# ======================================================= #
# ----- Task Listing Route ----- #


@router.get(
    "",
    response_model=TaskListResponse,
    responses={422: VALIDATION_RESPONSE},
)
async def list_tasks(
    query_params: TaskQueryParamsDep,
    service: TaskServiceDep,
) -> TaskListResponse:
    items, total = await service.list(params=query_params)
    return TaskListResponse.model_validate(
        {
            "items": items,
            "total": total,
            "limit": query_params.limit,
            "offset": query_params.offset,
        }
    )


# ======================================================= #
# ----- Task Get By Id Route ----- #


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={404: NOT_FOUND_RESPONSE},
)
async def get_task(
    task_id: TaskIdPath,
    service: TaskServiceDep,
) -> Task:
    return await service.get(task_id)


# ======================================================= #
# ----- Task Update Fully By Id Route ----- #


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def replace_task(
    task_id: TaskIdPath,
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    service: TaskServiceDep,
) -> Task:
    return await service.replace(task_id, **body.model_dump(), background_tasks=background_tasks)


# ======================================================= #
# ----- Task Update Partially By Id Route ----- #


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def patch_task(
    task_id: TaskIdPath,
    body: TaskPatch,
    background_tasks: BackgroundTasks,
    service: TaskServiceDep,
) -> Task:
    return await service.patch(
        task_id,
        fields=body.model_dump(exclude_unset=True),
        background_tasks=background_tasks,
    )


# ======================================================= #
# ----- Task Delete By Id  Route ----- #


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: NOT_FOUND_RESPONSE},
)
async def delete_task(
    task_id: TaskIdPath,
    background_tasks: BackgroundTasks,
    service: TaskServiceDep,
) -> None:
    await service.delete(task_id, background_tasks=background_tasks)
