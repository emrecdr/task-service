from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.core.config import settings
from app.core.database import init_schema
from app.core.errors import register_exception_handlers
from app.core.event_bus import EventBus
from app.core.health import router as health_router
from app.core.logging import RequestIDMiddleware, logger, setup_logging
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)

# Importing Task registers the ``tasks`` table on SQLModel.metadata so
# init_schema() can create it. The name itself is unused at module level.
from app.services.tasks.domain.models import Task  # noqa: F401
from app.services.tasks.infrastructure.listeners import log_event

_TASK_EVENTS = (TaskCreated, TaskUpdated, TaskStatusChanged, TaskCompleted, TaskDeleted)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_schema()
    bus = EventBus()
    for event_type in _TASK_EVENTS:
        bus.subscribe(event_type, log_event)
    app.state.event_bus = bus
    logger.info("startup_complete", app_env=settings.app_env)
    yield
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.project_name, lifespan=lifespan)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    return app


app = create_app()
