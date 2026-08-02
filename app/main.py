from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from prometheus_fastapi_instrumentator import Instrumentator

from app import __version__
from app.core.compression import ZstdMiddleware
from app.core.config import settings
from app.core.constants import ZSTD_MINIMUM_SIZE_BYTES, Environment
from app.core.database import dispose_engine
from app.core.diagnose import router as diagnose_router
from app.core.errors import register_exception_handlers
from app.core.event_bus import EventBus
from app.core.health import router as health_router
from app.core.logging import logger, setup_logging
from app.core.middleware import (
    BodySizeLimitMiddleware,
    RequestIDMiddleware,
    RequestTimeoutMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.tasks.api.v1.router import router as tasks_router
from app.services.tasks.infrastructure.listeners import register_listeners as register_task_listeners
from app.services.workflows.api.v1.router import router as workflow_router
from app.services.workflows.infrastructure.listeners import register_listeners as register_workflow_listeners
from app.services.workflows.infrastructure.seed import seed_workflow_if_missing


def custom_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()
    # Schema is owned by Alembic (``alembic upgrade head`` at deploy); tests create it
    # via the conftest fixture. Startup only ensures the workflow seed row exists.
    await seed_workflow_if_missing()
    bus = EventBus()
    register_task_listeners(bus)
    register_workflow_listeners(bus)
    app.state.event_bus = bus
    logger.info("startup_complete", app_env=settings.app_env)
    yield
    await dispose_engine()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        version=__version__,
        lifespan=lifespan,
        generate_unique_id_function=custom_unique_id,
    )
    # Middleware order matters: the last added is the OUTERMOST. RequestID must
    # wrap everything so request_id is bound (and X-Request-ID echoed) even on a
    # 413/504 produced by an inner hardening layer. Zstd is added first so it is
    # INNERMOST — it must wrap the router directly, because the BaseHTTPMiddleware
    # layers above re-frame responses into ``more_body`` chunks it would decline to
    # compress. Effective order per request:
    # RequestID → SecurityHeaders → CORS → BodySizeLimit → RequestTimeout → Zstd → app.
    app.add_middleware(ZstdMiddleware, minimum_size=ZSTD_MINIMUM_SIZE_BYTES)
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=settings.request_timeout_seconds)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=settings.app_env == Environment.PROD)
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(diagnose_router)
    app.include_router(tasks_router, prefix=settings.api_prefix)
    app.include_router(workflow_router, prefix=settings.api_prefix)
    # RED metrics (request count, latency, in-progress) at /metrics; kept out of
    # the OpenAPI schema so it stays an ops-only surface like the probes.
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    return app


app = create_app()
