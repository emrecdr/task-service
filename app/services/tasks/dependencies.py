from typing import Annotated

from fastapi import Depends, Header, Query

from app.core.dependencies import SessionDep
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.application.service import TaskService
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository


def get_task_service(session: SessionDep) -> TaskService:
    # Both repositories share the request's single session — the atomicity of the
    # read-workflow → check-move → write span (and the outbox write) depends on it.
    return TaskService(
        repo=SQLModelTaskRepository(session),
        workflows=SQLModelWorkflowRepository(session),
    )


def get_actor_roles(x_roles: Annotated[str | None, Header()] = None) -> frozenset[str]:
    """The acting caller's roles for workflow role-guards, from a comma-separated ``X-Roles``
    header. **Provisional and unauthenticated** — a stand-in until real auth lands, when the
    authenticated principal's roles are supplied here instead, with no engine/service change."""
    if not x_roles:
        return frozenset()
    return frozenset(role.strip() for role in x_roles.split(",") if role.strip())


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]

ActorRolesDep = Annotated[frozenset[str], Depends(get_actor_roles)]

TaskQueryParamsDep = Annotated[TaskListParams, Query()]
