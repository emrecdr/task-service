from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.config import settings
from app.core.database import init_schema
from app.core.errors import register_exception_handlers
from app.core.event_bus import EventBus
from app.core.health import router as health_router
from app.core.logging import logger, setup_logging
from app.core.middleware import RequestIDMiddleware
from app.services.tasks.api.v1.router import router as tasks_router
from app.services.tasks.infrastructure.listeners import register_listeners as register_task_listeners


def _resolve_version() -> str:
    try:
        return version("internal-task-service")
    except PackageNotFoundError:
        return "0.0.0"


def custom_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    init_schema()
    bus = EventBus()
    register_task_listeners(bus)
    app.state.event_bus = bus
    logger.info("startup_complete", app_env=settings.app_env)
    yield
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version=_resolve_version(),
        lifespan=lifespan,
        generate_unique_id_function=custom_unique_id,
    )
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(tasks_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
