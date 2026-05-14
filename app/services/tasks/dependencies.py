"""FastAPI dependency providers for the tasks feature.

Composes the repository (concrete adapter) and the application service
from the cross-cutting primitives in :mod:`app.core.dependencies`.
"""

from fastapi import Depends
from sqlmodel import Session

from app.core.dependencies import get_event_bus, get_session
from app.core.event_bus import EventBus
from app.services.tasks.application.service import TaskService
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.tasks.interfaces import TaskRepositoryInterface


def get_repository(session: Session = Depends(get_session)) -> TaskRepositoryInterface:
    return SQLModelTaskRepository(session)


def get_task_service(
    repo: TaskRepositoryInterface = Depends(get_repository),
    events: EventBus = Depends(get_event_bus),
) -> TaskService:
    return TaskService(repo=repo, events=events)
