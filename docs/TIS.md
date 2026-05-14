# 🏛️ Technical Implementation Specification (TIS)

**Project:** Internal Task Service
**Document Version:** 1.1
**Companion to:** `docs/PRD.md`, `docs/FRD.md`
**Source of Truth:** `docs/Python_Assignment.pdf`

---

## 1. Architecture Overview

The service follows **simplified Hexagonal Architecture (feature-first)** — each feature owns its full stack (`api/`, `application/`, `domain/`, `infrastructure/`) and exposes an explicit `interfaces.py` ABC for swappable storage. Substitutability and framework isolation are preserved; the ceremony of strict Cosmic-Python hex (separate `ports/` subfolder, Protocol typing, dedicated domain entity class apart from the SQLModel row, CI-enforced import boundaries) is dropped because it is not earned at this scale.

```
                                 ┌──────────────────────────┐
                                 │       Inbound (HTTP)      │
                                 │   app/services/tasks/api  │
                                 │   FastAPI router + DTOs   │
                                 └────────────┬─────────────┘
                                              │ calls
                                              ▼
       ┌──────────────────────────┐    ┌──────────────────────┐
       │  interfaces.py │    │   application/        │
       │  (ABC contracts)          │◄───┤   TaskService          │
       └────────────┬─────────────┘    └─────────┬────────────┘
                    ▲                            │ depends on
                    │ implements                 ▼
       ┌────────────┴─────────────┐    ┌──────────────────────┐
       │      infrastructure/       │    │       domain/         │
       │  SQLModelTaskRepository    │    │ Task (SQLModel +     │
       │  + listeners.py            │    │ table=True)          │
       │                            │    │ Status enum, events  │
       └──────────────────────────┘    └──────────────────────┘
```

**Architectural rules** (enforced by code review, not by `import-linter`):

1. `app/services/tasks/domain/**` may import the Python stdlib, `pydantic`, `sqlmodel`, and shared base classes from `app/core/`. It must not import from `fastapi`.
2. `app/services/tasks/application/**` may import domain + the interfaces module. It must not import from `infrastructure/` or from `fastapi`.
3. `app/services/tasks/infrastructure/**` may import everything in the feature plus database/session helpers from `app/core/`.
4. `app/services/tasks/api/**` is the only place inside the feature that touches `fastapi`.
5. `app/core/**` must not import from any individual service.

---

## 2. Project Structure

```text
task-service/
├── app/
│   ├── main.py                       # FastAPI app factory + lifespan
│   ├── core/                         # Cross-cutting concerns
│   │   ├── config.py                 # pydantic-settings Settings (env-aware)
│   │   ├── constants.py              # AppEnv enum, LogLevel mapping
│   │   ├── errors.py                 # ErrorCode enum + AppError hierarchy + handler registration
│   │   ├── event_bus.py              # In-process Event Bus + base Event
│   │   ├── logging.py                # structlog setup (env-aware) + RequestIDMiddleware
│   │   ├── health.py                 # /healthz, /readyz handlers
│   │   ├── database.py               # Session factory (SQLite :memory:, StaticPool)
│   │   └── dependencies.py           # Core DI providers (session, event bus)
│   └── services/
│       └── tasks/
│           ├── __init__.py
│           ├── dependencies.py       # Feature DI providers (repo, service)
│           ├── enums.py              # Status enum
│           ├── errors.py             # DuplicateTaskError, TaskNotFoundError, …
│           ├── interfaces.py         # TaskRepositoryInterface (ABC) at feature root
│           ├── api/
│           │   ├── __init__.py
│           │   └── v1/
│           │       ├── __init__.py
│           │       └── router.py     # POST/GET/PUT/PATCH/DELETE
│           ├── application/
│           │   ├── __init__.py
│           │   ├── service.py        # TaskService
│           │   └── dto.py            # TaskCreate, TaskPatch, TaskResponse, TaskListResponse
│           ├── domain/
│           │   ├── __init__.py
│           │   ├── models.py         # class Task(SQLModel, table=True) — source of truth
│           │   └── events.py         # 5 events
│           ├── infrastructure/
│           │   ├── __init__.py
│           │   ├── repository.py     # SQLModelTaskRepository(TaskRepositoryInterface)
│           │   └── listeners.py      # log_event listener
│           └── tests/                # UNIT tests only — fast, no FastAPI, no I/O
│               ├── __init__.py
│               ├── test_task_model.py
│               └── test_task_service.py
├── tests/                            # Cross-boundary tests at the project root
│   ├── conftest.py
│   ├── integration/                  # In-process FastAPI app + repo
│   │   ├── core/
│   │   │   ├── test_error_envelope.py
│   │   │   └── test_request_id_propagation.py
│   │   └── services/
│   │       └── tasks/
│   │           ├── test_create_task.py
│   │           ├── test_list_tasks.py
│   │           ├── test_get_task.py
│   │           ├── test_put_task.py
│   │           ├── test_patch_task.py
│   │           ├── test_delete_task.py
│   │           └── test_repository_sqlmodel.py
│   ├── contract/                     # Port-conformance tests (parametrized over impls)
│   │   └── test_task_repository_interface.py
│   ├── hurl/                         # E2E scenarios in Hurl format
│   │   ├── healthz.hurl
│   │   ├── readyz.hurl
│   │   ├── request_id_propagation.hurl
│   │   ├── task_create.hurl
│   │   ├── task_create_duplicate_title.hurl
│   │   ├── task_create_validation_errors.hurl
│   │   ├── task_lifecycle.hurl
│   │   ├── task_list_filter_sort.hurl
│   │   ├── task_put_full_replace.hurl
│   │   ├── task_patch_partial.hurl
│   │   └── task_not_found.hurl
│   └── e2e/                          # OpenAPI-driven property tests + future container E2E
│       ├── .gitkeep
│       └── test_schemathesis.py      # optional in Phase 1
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yaml
├── docs/                             # PRD.md, FRD.md, TIS.md, …
├── reports/
│   └── hurl/                         # Hurl JSON/HTML reports (gitignored)
├── pyproject.toml                    # uv-managed
├── uv.lock
├── ruff.toml
├── mypy.ini
├── Makefile                          # `make hurl-e2e`, `make test`, `make lint`
├── .env.example                      # checked-in reference template
├── .env.dev                          # local development (gitignored)
├── .env.test                         # automated tests (gitignored)
├── .env.qa                           # QA / pre-prod (gitignored)
├── .env.prod                         # production (gitignored)
├── .dockerignore                     # excludes .env.* from the image
├── .pre-commit-config.yaml
└── README.md
```

> **Test split rule of thumb:** _can this test run with only my feature module imported?_ If yes → it's unit, lives in `app/services/<feature>/tests/`. If it needs `app.main.app`, real HTTP, or another feature → it crosses a boundary and lives under `tests/` at the project root.

---

## 3. Domain Layer

The domain layer holds the SQLModel-backed `Task` entity (which doubles as the storage row), the `Status` enum, the five domain events, and domain-typed exceptions.

### 3.1 `Task` model and `Status` enum

```python
# app/services/tasks/enums.py
from enum import StrEnum


class Status(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
```

```python
# app/services/tasks/domain/models.py
from datetime import UTC, datetime
from sqlmodel import Field, SQLModel

from app.services.tasks.enums import Status


class Task(SQLModel, table=True):
    """The Task entity — source of truth for both DB row and domain logic."""

    __tablename__ = "tasks"

    id: int | None = Field(default=None, primary_key=True)
    title: str = Field(min_length=1, max_length=200)
    title_key: str = Field(index=True, unique=True, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Status = Field(default=Status.NEW)
    priority: int = Field(ge=1, le=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)

    @staticmethod
    def normalize_title(title: str) -> str:
        """Comparison key used for case-insensitive uniqueness checks."""
        return title.strip().casefold()

    @classmethod
    def from_input(cls, *, title: str, description: str | None, status: Status, priority: int) -> "Task":
        cleaned = title.strip()
        if not cleaned:
            raise ValueError("title must not be empty")
        return cls(
            title=cleaned,
            title_key=cls.normalize_title(cleaned),
            description=description,
            status=status,
            priority=priority,
        )
```

The `title_key` column is the canonical uniqueness key (case-insensitive, trimmed). The original `title` is preserved verbatim for display.

### 3.2 Domain events

```python
# app/services/tasks/domain/events.py
from app.core.event_bus import Event
from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status


class TaskCreated(Event):
    task: Task


class TaskUpdated(Event):
    task: Task
    previous: Task
    changed_fields: list[str]


class TaskStatusChanged(Event):
    task: Task
    from_status: Status
    to_status: Status


class TaskCompleted(Event):
    task: Task


class TaskDeleted(Event):
    task: Task
```

All five events ship from day one. `TaskCompleted` is a convenience event derived from `TaskStatusChanged`; future listeners can subscribe to it without filtering payloads. `TaskUpdated` is the catch-all hook for audit/cache-invalidation listeners.

### 3.3 Feature-level errors

```python
# app/services/tasks/errors.py
from app.core.errors import ConflictError, ErrorCode, NotFoundError, ValidationError


class DuplicateTaskError(ConflictError):
    error_code = ErrorCode.DUPLICATE_TASK
    detail = "A task with this title already exists."


class TaskNotFoundError(NotFoundError):
    error_code = ErrorCode.TASK_NOT_FOUND
    detail = "Task not found."


class EmptyUpdateError(ValidationError):
    error_code = ErrorCode.EMPTY_UPDATE
    detail = "PATCH body must contain at least one field."


class ReadOnlyFieldError(ValidationError):
    error_code = ErrorCode.READ_ONLY_FIELD
    detail = "Field is server-managed and cannot be set by the caller."
```

Base classes (`AppError`, `ConflictError`, `NotFoundError`, `ValidationError`) live in `app/core/errors.py` (see §7.1).

---

## 4. Repository Interface (ABC)

```python
# app/services/tasks/interfaces.py
from abc import ABC, abstractmethod
from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status


class TaskRepositoryInterface(ABC):
    """Storage contract for Task. Implementations live in infrastructure/."""

    @abstractmethod
    def add(self, *, title: str, description: str | None,
            status: Status, priority: int) -> Task: ...

    @abstractmethod
    def get(self, task_id: int) -> Task: ...                       # raises TaskNotFoundError

    @abstractmethod
    def list(
        self,
        *,
        statuses: list[Status] | None,
        sort: str,                                                 # "priority_asc" | "priority_desc"
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]: ...                               # (items, total)

    @abstractmethod
    def replace(self, task_id: int, *, title: str, description: str | None,
                status: Status, priority: int) -> Task: ...

    @abstractmethod
    def patch(self, task_id: int, **fields: object) -> Task: ...

    @abstractmethod
    def delete(self, task_id: int) -> Task: ...                    # returns deleted snapshot
```

`ABC + @abstractmethod` is chosen over `Protocol` for clearer runtime errors when an implementation forgets a method — they are raised at instantiation time, not at the first call.

---

## 5. Application Layer

```python
# app/services/tasks/application/service.py
from fastapi import BackgroundTasks

from app.core.event_bus import EventBus
from app.services.tasks.domain.events import (
    TaskCompleted, TaskCreated, TaskDeleted, TaskStatusChanged, TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status
from app.services.tasks.errors import EmptyUpdateError
from app.services.tasks.interfaces import TaskRepositoryInterface


class TaskService:
    def __init__(self, *, repo: TaskRepositoryInterface, events: EventBus) -> None:
        self._repo = repo
        self._events = events

    async def create(
        self, *, title: str, description: str | None, status: Status, priority: int,
        background_tasks: BackgroundTasks,
    ) -> Task:
        task = self._repo.add(title=title, description=description,
                              status=status, priority=priority)
        await self._events.publish(TaskCreated(task=task), background_tasks)
        return task

    async def patch(
        self, task_id: int, *, fields: dict[str, object],
        background_tasks: BackgroundTasks,
    ) -> Task:
        if not fields:
            raise EmptyUpdateError()
        previous = self._repo.get(task_id)
        updated = self._repo.patch(task_id, **fields)
        changed = [f for f in fields if getattr(updated, f) != getattr(previous, f)]
        if not changed:
            return updated
        await self._events.publish(
            TaskUpdated(task=updated, previous=previous, changed_fields=changed),
            background_tasks,
        )
        if "status" in changed:
            await self._events.publish(
                TaskStatusChanged(task=updated,
                                  from_status=previous.status,
                                  to_status=updated.status),
                background_tasks,
            )
            if updated.status is Status.COMPLETED:
                await self._events.publish(TaskCompleted(task=updated), background_tasks)
        return updated

    # replace(), delete(), list(), get() follow the same shape.
```

```python
# app/services/tasks/application/dto.py
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field

from app.services.tasks.enums import Status


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Status = Status.NEW
    priority: int = Field(ge=1, le=5)


class TaskPatch(BaseModel):
    """All fields optional; at least one must be supplied (enforced in service)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    status: Status | None = None
    priority: int | None = Field(default=None, ge=1, le=5)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    status: Status
    priority: int
    created_at: datetime


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
    limit: int
    offset: int
```

`TaskUpdate` (PUT) reuses `TaskCreate` since PUT requires every field — no second class needed.

---

## 6. Infrastructure

### 6.1 `SQLModelTaskRepository`

> **Why `StaticPool` for SQLite `:memory:`?** SQLAlchemy's default connection pool gives each new connection its own private `:memory:` database — meaning the schema you created in one connection is invisible to the next. Without intervention, the test suite, the FastAPI app, and the readiness probe all see different empty databases. **`poolclass=StaticPool` + `connect_args={"check_same_thread": False}`** forces every connection to share one in-memory DB. This is a Phase 1 quirk of the storage choice; it disappears the day Postgres replaces SQLite. The session factory in `app/core/database.py` configures it once.

```python
# app/services/tasks/infrastructure/repository.py
from sqlalchemy import select as sa_select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface


class SQLModelTaskRepository(TaskRepositoryInterface):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, *, title, description, status, priority) -> Task:
        try:
            task = Task.from_input(title=title, description=description,
                                   status=status, priority=priority)
            self._session.add(task)
            self._session.commit()
            self._session.refresh(task)
            return task
        except IntegrityError as e:
            self._session.rollback()
            if "title_key" in str(e.orig):
                raise DuplicateTaskError(details={"title": title}) from e
            raise

    def get(self, task_id: int) -> Task:
        task = self._session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(details={"id": task_id})
        return task

    def list(self, *, statuses, sort, limit, offset) -> tuple[list[Task], int]:
        stmt = sa_select(Task)
        if statuses:
            stmt = stmt.where(Task.status.in_(statuses))
        order_col = Task.priority.desc() if sort == "priority_desc" else Task.priority.asc()
        stmt = stmt.order_by(order_col, Task.created_at.asc())

        total_stmt = sa_select(Task)
        if statuses:
            total_stmt = total_stmt.where(Task.status.in_(statuses))
        total = self._session.scalars(total_stmt).all()

        items = self._session.scalars(stmt.offset(offset).limit(limit)).all()
        return list(items), len(total)

    # replace(), patch(), delete() omitted for brevity — same pattern.
```

### 6.2 Logging listener

```python
# app/services/tasks/infrastructure/listeners.py
from app.core.event_bus import Event
from app.core.logging import logger


async def log_event(event: Event) -> None:
    logger.info(
        "domain_event",
        event_type=type(event).__name__,
        event_id=str(event.id),
        task_id=getattr(event, "task", None) and event.task.id,
    )
```

Subscribed at startup to all five events (see §7.7).

### 6.3 FastAPI router

```python
# app/services/tasks/api/v1/router.py
from typing import Literal
from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from app.services.tasks.application.dto import (
    TaskCreate, TaskListResponse, TaskPatch, TaskResponse,
)
from app.services.tasks.application.service import TaskService
from app.services.tasks.dependencies import get_task_service
from app.services.tasks.enums import Status

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=TaskResponse)
async def create_task(
    body: TaskCreate,
    background_tasks: BackgroundTasks,
    service: TaskService = Depends(get_task_service),
):
    return await service.create(**body.model_dump(), background_tasks=background_tasks)


@router.get("", response_model=TaskListResponse)
def list_tasks(
    statuses: list[Status] | None = Query(default=None, alias="status"),
    sort: Literal["priority_asc", "priority_desc"] = "priority_desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: TaskService = Depends(get_task_service),
):
    items, total = service.list(statuses=statuses, sort=sort, limit=limit, offset=offset)
    return TaskListResponse(items=items, total=total, limit=limit, offset=offset)
```

The feature router is mounted in `app/main.py` (§7.7) under `settings.api_v1_prefix`.

---

## 7. Cross-Cutting Infrastructure

### 7.1 `AppError`, `ErrorCode`, and the global handler

All three error concerns — the stable code enum, the exception hierarchy, and the FastAPI exception handler — live in **one file** because they are always read and changed together.

```python
# app/core/errors.py
from enum import StrEnum
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    EMPTY_UPDATE = "empty_update"
    READ_ONLY_FIELD = "read_only_field"
    DUPLICATE_TASK = "duplicate_task"
    TASK_NOT_FOUND = "task_not_found"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    detail: str = "An unexpected internal server error occurred."
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, *, detail: str | None = None,
                 details: dict | None = None,
                 original_error: Exception | None = None) -> None:
        if detail is not None:
            self.detail = detail
        self.details = details or {}
        self.original_error = original_error
        super().__init__(self.detail)


class ValidationError(AppError):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = ErrorCode.VALIDATION_ERROR


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND


def register_exception_handlers(app: FastAPI) -> None:
    """Translate AppError → standardized JSON envelope."""

    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {
                "code": str(exc.error_code),
                "message": exc.detail,
                "details": exc.details,
                "request_id": getattr(request.state, "request_id", None),
            }},
        )
```

Consumers can switch on `error.code` without parsing English strings.

### 7.2 Event Bus

```python
# app/core/event_bus.py
import collections
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: UUID = Field(default_factory=uuid4)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[type[Event], list[Callable]] = collections.defaultdict(list)

    def subscribe(self, event_type: type[Event], handler: Callable) -> None:
        self._listeners[event_type].append(handler)

    async def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        for handler in self._listeners[type(event)]:
            background_tasks.add_task(handler, event)
```

**Phase 1 deliberately omits:** tenacity retry, dead-letter queues, circuit breakers, deduplication. They have not earned their weight at this scale. Listed in PRD §12 (Roadmap) if future requirements justify them.

### 7.3 Structured logging (`structlog`)

```python
# app/core/logging.py
import sys, structlog
from app.core.config import settings


def setup_logging() -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(settings.log_level_int),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

logger = structlog.get_logger("app")
```

`structlog` is the standard structured-logging library for production Python services — JSON output in deployed environments, human-readable output in `dev`, and `contextvars`-based context binding that the Request-ID middleware leverages.

### 7.4 Request-ID middleware

Lives in the same `app/core/logging.py` file — its only purpose is to bind a request-scoped identifier into the `structlog` context so every log line for the request carries it.

```python
# app/core/logging.py (continued)
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or str(uuid4())
        request.state.request_id = rid
        structlog.contextvars.bind_contextvars(request_id=rid)
        try:
            response = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        response.headers["X-Request-ID"] = rid
        return response
```

### 7.5 Health endpoints

```python
# app/core/health.py
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.dependencies import get_session

router = APIRouter()


@router.get("/healthz")
def liveness():
    return {"status": "ok"}


@router.get("/readyz")
def readiness(session = Depends(get_session)):
    try:
        session.scalar(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse({"status": "not_ready", "error": str(e)}, status_code=503)
```

### 7.6 Configuration

The active `.env.*` file is chosen at module import time from `APP_ENV`:

```python
# app/core/config.py
import logging, os
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


AppEnv = Literal["dev", "test", "qa", "prod"]


def _resolve_env_file() -> str | None:
    """Pick the .env.<APP_ENV> file at the project root, or None if absent."""
    env = os.getenv("APP_ENV", "dev")
    candidate = Path(__file__).resolve().parents[2] / f".env.{env}"
    return str(candidate) if candidate.is_file() else None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = "dev"
    project_name: str = "Internal Task Service"
    api_v1_prefix: str = "/v1"
    database_url: str = "sqlite+pysqlite:///:memory:"
    log_level: str | None = None
    default_list_limit: int = 50
    max_list_limit: int = 500

    @property
    def log_level_int(self) -> int:
        default_by_env = {
            "dev": logging.DEBUG,
            "test": logging.WARNING,
            "qa": logging.INFO,
            "prod": logging.INFO,
        }
        if self.log_level is None:
            return default_by_env[self.app_env]
        return logging.getLevelName(self.log_level)

    @property
    def json_logs(self) -> bool:
        return self.app_env in {"qa", "prod"}

    @property
    def expose_stack_traces(self) -> bool:
        return self.app_env == "dev"


settings = Settings()
```

**File-loading rules** (must match FRD §6.1):

- `.env.example` is the only `.env.*` file checked into VCS and is **never** loaded at runtime.
- `.env.dev`, `.env.test`, `.env.qa`, `.env.prod` are all listed in `.gitignore` and `.dockerignore`.
- The Docker image takes configuration exclusively from real environment variables; no file is mounted by default.
- Test runs set `APP_ENV=test` in `tests/conftest.py` so pytest deterministically reads `.env.test`.

### 7.7 Lifespan, app factory, custom OpenAPI IDs

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.event_bus import EventBus
from app.core import health
from app.core.logging import RequestIDMiddleware, logger, setup_logging
from app.services.tasks.api.v1.router import router as tasks_router
from app.services.tasks.domain.events import (
    TaskCompleted, TaskCreated, TaskDeleted, TaskStatusChanged, TaskUpdated,
)
from app.services.tasks.infrastructure.listeners import log_event


def custom_unique_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    bus = EventBus()
    for ev in (TaskCreated, TaskUpdated, TaskStatusChanged, TaskCompleted, TaskDeleted):
        bus.subscribe(ev, log_event)
    app.state.event_bus = bus
    logger.info("startup_complete")
    yield
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.project_name,
        lifespan=lifespan,
        generate_unique_id_function=custom_unique_id,
    )
    app.add_middleware(RequestIDMiddleware)
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(tasks_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
```

---

## 8. Dependency Injection

Core providers live in `app/core/dependencies.py`. Feature-specific providers live in the feature's own `dependencies.py` — keeps the wiring close to the code it wires.

```python
# app/core/dependencies.py
from typing import Generator
from fastapi import Request
from sqlmodel import Session

from app.core.database import session_factory
from app.core.event_bus import EventBus


def get_session() -> Generator[Session, None, None]:
    with session_factory() as session:
        yield session


def get_event_bus(request: Request) -> EventBus:
    return request.app.state.event_bus
```

```python
# app/services/tasks/dependencies.py
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
```

The SQLite `:memory:` engine is built with `connect_args={"check_same_thread": False}, poolclass=StaticPool` so the test suite and the running app share one schema. See §6.1 for the full rationale (the next developer adding a test fixture or extra worker will trip on this if it's not loud).

---

## 9. Testing Strategy

The project uses a **hybrid layout**: unit tests live with the feature module, every other category lives under the project-root `tests/` directory.

| Test type           | Where it lives                  | What it touches                                       | Speed           |
| ------------------- | ------------------------------- | ----------------------------------------------------- | --------------- |
| **Unit**            | `app/services/<feature>/tests/` | Pure Python; no FastAPI, no DB I/O                    | Milliseconds    |
| **Integration**     | `tests/integration/`            | Full FastAPI app + in-memory repo, in-process         | Hundreds of ms  |
| **Contract**        | `tests/contract/`               | One file per port, parametrized over all impls        | Hundreds of ms  |
| **E2E (Hurl)**      | `tests/hurl/`                   | Real HTTP against container                           | Seconds         |
| **E2E (property)**  | `tests/e2e/`                    | OpenAPI-driven via Schemathesis (optional in Phase 1) | Tens of seconds |
| **Load (Phase 2+)** | `tests/load/`                   | Locust workload profiles                              | Minutes         |

### 9.1 `pyproject.toml` — pytest config

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["app/services", "tests"]                 # both roots discovered
python_files = ["test_*.py"]
addopts = "--import-mode=importlib --cov=app --cov-report=term --cov-fail-under=80"
markers = [
  "unit: pure in-module tests",
  "integration: FastAPI app + repo, in-process",
  "contract: port-conformance tests",
  "e2e: external network / container",
]
```

### 9.2 Hurl E2E scenarios

Hurl files use plain descriptive filenames — one scenario per file.

```
tests/hurl/
├── healthz.hurl                              # GET /healthz
├── readyz.hurl                               # GET /readyz
├── request_id_propagation.hurl               # X-Request-ID round-trip
├── task_create.hurl                          # POST 201 + capture id
├── task_create_duplicate_title.hurl          # 409 duplicate_task envelope
├── task_create_validation_errors.hurl        # 422 across fields
├── task_lifecycle.hurl                       # create → in_progress → completed → delete
├── task_list_filter_sort.hurl                # ?status=&sort=&limit=&offset=
├── task_put_full_replace.hurl                # PUT semantics
├── task_patch_partial.hurl                   # PATCH + empty-body 422
└── task_not_found.hurl                       # 404 task_not_found envelope
```

Example file:

```hurl
# tests/hurl/task_lifecycle.hurl
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "ship hurl tests",
  "priority": 4
}
HTTP 201
[Captures]
task_id: jsonpath "$.id"
[Asserts]
jsonpath "$.title" == "ship hurl tests"
jsonpath "$.status" == "new"
header "X-Request-ID" matches "[0-9a-f-]{36}"

PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 200
[Asserts]
jsonpath "$.status" == "in_progress"

PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 200

DELETE {{base_url}}/v1/tasks/{{task_id}}
HTTP 204

GET {{base_url}}/v1/tasks/{{task_id}}
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
```

Hurl reports are written to `reports/hurl/` (HTML + JSON) and uploaded as CI artifacts.

### 9.3 Schemathesis (optional, OpenAPI-driven)

```python
# tests/e2e/test_schemathesis.py
import schemathesis

schema = schemathesis.from_uri("http://localhost:8000/openapi.json")


@schema.parametrize()
def test_no_5xx(case):
    response = case.call()
    case.validate_response(response)
```

Complements the Hurl scenario tests by generating property-based cases the human writer never thought of. Phase 1 ships it as opt-in; Phase 2 wires it into the default CI pipeline.

### 9.4 Coverage gate

`pytest --cov=app --cov-fail-under=80` runs against unit + integration + contract layers. Hurl and Schemathesis do not contribute to the Python coverage number — they assert behavior, not code coverage.

---

## 10. Tooling

### 10.1 `pyproject.toml` (highlights)

```toml
[project]
name = "internal-task-service"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.30",
    "sqlmodel>=0.0.27",
    "pydantic[email]>=2.5",
    "pydantic-settings>=2.1",
    "structlog>=25.0",
]

[dependency-groups]
dev = [
    "pytest>=8.4",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "httpx>=0.27",
    "ruff>=0.6",
    "mypy>=1.10",
    "bandit[toml]>=1.7",
    "pre-commit>=4.0",
    "schemathesis>=3.30",
]

[tool.bandit]
exclude_dirs = ["tests", ".venv", "app/services/**/tests"]
skips = ["B101"]
severity = "medium"

[tool.ruff]
line-length = 120
target-version = "py313"

[tool.mypy]
python_version = "3.13"
strict = true
files = ["app", "tests"]
```

> `import-linter` is **not** in dev deps — boundaries are enforced by code review. Reintroducing it is a Phase 2 option if the team grows beyond one squad.

### 10.2 `Dockerfile`

```dockerfile
# docker/Dockerfile
FROM python:3.13-slim AS base
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app
EXPOSE 8000
ENV APP_ENV=prod \
    TZ=UTC                          # enforce UTC at the container level (FRD §2.4)
USER 1000:1000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 10.3 Pre-commit (`.pre-commit-config.yaml`)

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
      - id: check-toml
      - id: check-merge-conflict
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.9
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/PyCQA/bandit
    rev: 1.7.10
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml"]
        additional_dependencies: ["bandit[toml]"]
  - repo: local
    hooks:
      - id: uv-lock-check
        name: uv lock is up to date
        entry: uv lock --check
        language: system
        pass_filenames: false
```

Onboarding:

```bash
uv sync --all-groups
uv run pre-commit install
```

### 10.4 `Makefile`

```makefile
.PHONY: install lint typecheck test test-unit test-integration hurl-e2e schemathesis

install:
	uv sync --all-groups
	uv run pre-commit install

lint:
	uv run ruff check
	uv run ruff format --check
	uv run bandit -c pyproject.toml -r app

typecheck:
	uv run mypy app tests

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

hurl-e2e:
	docker compose -f docker/docker-compose.yaml up -d task-service
	hurl --test \
	     --variable base_url=http://localhost:8000 \
	     --report-html reports/hurl/ \
	     --report-json reports/hurl/report.json \
	     tests/hurl/
	docker compose -f docker/docker-compose.yaml down

schemathesis:
	docker compose -f docker/docker-compose.yaml up -d task-service
	uv run schemathesis run http://localhost:8000/openapi.json --checks all
	docker compose -f docker/docker-compose.yaml down
```

### 10.5 CI (representative pipeline)

1. `make install` (uv sync + pre-commit install)
2. `uv run pre-commit run --all-files` # ruff, ruff-format, bandit, file hygiene
3. `make typecheck` # mypy
4. `make test` # pytest + coverage gate at 80%
5. `make hurl-e2e` # Hurl scenarios against container
6. (optional) `make schemathesis` # OpenAPI fuzz
7. `docker build .`

Any step failing fails the build. Hurl reports (`reports/hurl/*.html`) are uploaded as CI artifacts.

---

## 11. Performance, Concurrency, and Time

- **Single uvicorn worker** assumed in Phase 1. The SQLite `:memory:` engine cannot be safely shared across workers without `StaticPool` + a single process, so this is enforced.
- **`async def` routes** are used everywhere; the SQLModel repository is synchronous and runs in the default threadpool. Acceptable for an in-memory store. When Postgres lands, swap to `async` SQLAlchemy at the adapter boundary — domain and service layers are untouched.
- **Event handlers** run via `BackgroundTasks`, i.e. after the HTTP response is returned to the client. They do not affect request latency.
- **Time is UTC everywhere** (FRD §2.4). Three layers enforce this:
  1. **Container:** `ENV TZ=UTC` in the Dockerfile so library fallbacks to system time still produce UTC.
  2. **Code:** `datetime.now(UTC)` is the only constructor used; naive `datetime` is treated as a bug. A unit test (`app/services/tasks/tests/test_task_model.py`) asserts `Task.created_at.tzinfo is not None`.
  3. **Logs:** `structlog.processors.TimeStamper(fmt="iso", utc=True)` produces ISO-8601 UTC strings in every log line, with no offset suffix.
     Distributed-team safety: every stand-up reference to "the task created at 14:01" is unambiguous because the timestamp the API returned is UTC by contract.

---

## 12. Security Posture (Phase 1)

The service is internal and unauthenticated in Phase 1. To avoid accidentally publishing it to the internet:

- The Dockerfile binds to `0.0.0.0:8000` but **does not** publish the port by default in `docker-compose.yaml`; the operator must opt in.
- CORS is **off** by default (no `CORSMiddleware`). Phase 2 will introduce a configured allow-list when the SPA lands.
- All inputs are validated by Pydantic; no string concatenation reaches SQL — SQLModel parameterizes everything.
- Error responses **never** include stack traces in `qa` or `prod` (per FRD §6); only `dev` exposes them.
- `bandit` runs in CI to catch common Python security pitfalls.

---

## 13. Best Practices Summary

1. **Feature-first hex**: each feature owns its full stack — `api/`, `application/`, `domain/`, `infrastructure/`, plus flat `interfaces.py`, `dependencies.py`, `errors.py` at the feature root.
2. **Two Pydantic models per entity**: SQLModel `Task` is the source of truth (domain + storage); API DTOs are separate so the wire format evolves independently of the schema.
3. **ABC-based interfaces** at the feature root — clearer instantiation-time errors than `Protocol`.
4. **Errors carry stable codes**: API consumers can switch on `error.code` without parsing English strings.
5. **Events fire after writes succeed**, never before — listeners can trust the world.
6. **Listeners do not block responses** — `BackgroundTasks` keeps the request path fast.
7. **Contract tests** pin the repository interface so swapping adapters in Phase 2 is a one-file change with free conformance checking.
8. **Hybrid test layout** — unit next to code, everything cross-boundary at root.
9. **Hurl for E2E**, one scenario per file with plain descriptive names.
10. **Configuration is environment-aware** via a single `APP_ENV` switch, with per-env `.env.*` files.
11. **Structured logs everywhere**, with `request_id` correlation by middleware.

---

## 14. Phase 2 Hooks

This TIS leaves a clean, mechanical path for the Phase 2 work scoped by PRD §12 and FRD §12. The hooks the implementation must preserve:

- Adding a `PostgresTaskRepository` is **one file** under `infrastructure/` plus a one-line DI swap in `dependencies.py`. The application and domain layers do not change.
- Adding **Alembic** migrations is additive — no Phase 1 file is touched.
- Adding **slowapi** as a middleware is additive at `app/main.py`.
- Adding a `SlackListener` is one new file subscribed to `TaskCompleted` via the existing `EventBus`.
- Promoting `Schemathesis` to a required CI step is a Makefile/pipeline change only.
- Reintroducing `import-linter` (if the team grows beyond one squad) is a config-only change.

Detailed Phase 2 designs (RBAC auth module, Workflow Phase module, Slack adapter, Postgres adapter, `/metrics`, etc.) live in PRD §12 and FRD §12. They are deliberately **not** described in this TIS because this document specifies what is being implemented now; future-phase implementations will get their own TIS revisions when the work is scheduled.
