import uuid
from typing import Annotated

from fastapi import APIRouter, Path, status

from app.core.openapi_responses import (
    CONFLICT_RESPONSE,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    PATCH_VALIDATION_RESPONSE,
    VALIDATION_RESPONSE,
    WRITE_VALIDATION_RESPONSE,
)
from app.services.tasks.application.dto import (
    TaskCreate,
    TaskListResponse,
    TaskPatch,
    TaskResponse,
    TaskTransitionsResponse,
)
from app.services.tasks.dependencies import ActorRolesDep, TaskQueryParamsDep, TaskServiceDep
from app.services.tasks.domain.models import Task

TaskIdPath = Annotated[uuid.UUID, Path()]

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ``tags`` is not a Task column — it lives in the tags feature's join — so responses are built
# explicitly instead of being coerced straight off the ORM row. The list path takes one batch
# query for the whole page; a per-row lookup is exactly what would make that endpoint N+1.


async def _one(service: TaskServiceDep, task: Task) -> TaskResponse:
    response = TaskResponse.model_validate(task)
    response.tags = (await service.tags_for([task.id])).get(task.id, [])
    return response


async def _many(service: TaskServiceDep, tasks: list[Task]) -> list[TaskResponse]:
    by_task = await service.tags_for([task.id for task in tasks])
    responses: list[TaskResponse] = []
    for task in tasks:
        response = TaskResponse.model_validate(task)
        response.tags = by_task.get(task.id, [])
        responses.append(response)
    return responses


# ======================================================= #
# ----- Task Create Route ----- #


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    responses={
        # No 403: a create resolves an entry state, never a role-guarded transition.
        409: CONFLICT_RESPONSE,
        422: WRITE_VALIDATION_RESPONSE,
    },
)
async def create_task(
    body: TaskCreate,
    service: TaskServiceDep,
) -> TaskResponse:
    return await _one(service, await service.create(**body.model_dump()))


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
            "items": await _many(service, items),
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
    responses={
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def get_task(
    task_id: TaskIdPath,
    service: TaskServiceDep,
) -> TaskResponse:
    return await _one(service, await service.get(task_id))


# ======================================================= #
# ----- Task Legal Transitions Route ----- #


@router.get(
    "/{task_id}/transitions",
    response_model=TaskTransitionsResponse,
    responses={
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def task_transitions(
    task_id: TaskIdPath,
    service: TaskServiceDep,
) -> TaskTransitionsResponse:
    task, transitions = await service.legal_moves(task_id)
    return TaskTransitionsResponse.model_validate(
        {
            "task_id": task.id,
            "status": task.status,
            "transitions": [{"name": t.name, "to": t.to_state, "meta": dict(t.meta)} for t in transitions],
        }
    )


# ======================================================= #
# ----- Task Update Fully By Id Route ----- #


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: WRITE_VALIDATION_RESPONSE,
    },
)
async def replace_task(
    task_id: TaskIdPath,
    body: TaskCreate,
    service: TaskServiceDep,
    roles: ActorRolesDep,
) -> TaskResponse:
    return await _one(service, await service.replace(task_id, **body.model_dump(), roles=roles))


# ======================================================= #
# ----- Task Update Partially By Id Route ----- #


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        403: FORBIDDEN_RESPONSE,
        404: NOT_FOUND_RESPONSE,
        409: CONFLICT_RESPONSE,
        422: PATCH_VALIDATION_RESPONSE,
    },
)
async def patch_task(
    task_id: TaskIdPath,
    body: TaskPatch,
    service: TaskServiceDep,
    roles: ActorRolesDep,
) -> TaskResponse:
    task = await service.patch(
        task_id,
        fields=body.model_dump(exclude_unset=True),
        roles=roles,
    )
    return await _one(service, task)


# ======================================================= #
# ----- Task Delete By Id Route ----- #


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: NOT_FOUND_RESPONSE,
        422: VALIDATION_RESPONSE,
    },
)
async def delete_task(
    task_id: TaskIdPath,
    service: TaskServiceDep,
) -> None:
    await service.delete(task_id)
