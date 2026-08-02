# Architecture — Python / FastAPI

> **Precedence:** where this template and the project's `CLAUDE.md` disagree, **CLAUDE.md wins**. The sections below have been tailored to this repo; treat remaining generic advice (Alembic, CORS, JWT, cursor pagination) as Phase-2 reference material, not current requirements.

## Pattern: Clean / Hexagonal / Onion Architecture

Dependencies flow inward: outer layers depend on inner layers, never the reverse.

```
API (presentation) -> Application (use cases) -> Domain (entities)
         |                    |
    Infrastructure (adapters, repositories)
```

## Layer Responsibilities

### Domain Layer (`domain/`)

- Business entities, value objects, enums
- No external dependencies — pure Python
- Defines what the business IS

### Application Layer (`application/`)

- Use cases, services, DTOs
- Depends only on domain layer
- Orchestrates business operations
- Defines what the system DOES

### Infrastructure Layer (`infrastructure/`)

- Database repositories, external API clients, message queues
- Implements application-layer interfaces
- Adapts external systems to domain contracts

### Presentation Layer (`api/v1/`)

- FastAPI routes, request/response schemas
- Thin — delegates to application services immediately
- Handles HTTP concerns only (status codes, headers, serialization)

## Service Module Structure

```
app/services/<service_name>/
    domain/
        models.py           # SQLModel entities (+ events.py; enums live in constants.py)
    application/
        service.py          # Business logic
        dto.py              # Data transfer objects
    infrastructure/
        repository.py       # Database access implementations
    api/v1/
        router.py           # FastAPI router
    interfaces.py           # Repository contracts (module root)
    serialization.py        # Wire-format boundary (module root, only when the feature owns a document format)
    constants.py            # StrEnums + Final bounds (single file — no separate enums.py)
    errors.py               # Custom exceptions (module root; never exceptions.py)
    dependencies.py         # Feature DI wiring
    tests/                  # Feature-local UNIT tests only (flat; integration lives in tests/ at repo root)
    MODULE.md               # Module documentation
```

## Repository Pattern

- **Interfaces** defined at module root: `interfaces.py`
- **Implementations** in `infrastructure/repository.py`
- Repositories own all data access for their domain tables
- Services inject repository interfaces via dependency injection

## Cross-Service Data Access

- Inject the owning module's repository interface via DI
- Never add methods to a repository that query another service's domain
- Never duplicate repository logic across module boundaries
- If you need data from another service, inject that service's repository interface

## Dependency Injection

- FastAPI `Depends()` for wiring dependencies
- Repository implementations injected into services
- Services injected into route handlers
- Configuration via Pydantic `Settings` classes

## Module Documentation

- Every service module MUST maintain a `MODULE.md` file
- Documents: responsibilities, models, capabilities, endpoints, dependencies
- Updated whenever the module changes (models, endpoints, dependencies)

## Scope-Based Data Filtering

- Services implement role-based access using user context
- Repository validates scope and filters data accordingly
- Unsupported scopes return empty results with warning (graceful degradation)

## Health & Readiness Endpoints

Every service exposes two probes:

```python
@router.get("/health")     # Liveness: is the process alive?
async def health():
    return {"status": "ok"}

@router.get("/ready")      # Readiness: can it serve traffic?
async def readiness(db: DbSession):
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}
```

- Wire into Kubernetes probes or Docker HEALTHCHECK
- Readiness checks dependencies (DB, cache, message broker)
- Liveness never checks dependencies — only whether the process is responsive

## Observability

### Structured Logging

Use `structlog` for structured JSON logging — never bare `logging.info(f"...")`:

```python
import structlog
logger = structlog.get_logger()

# Bind request context via middleware
structlog.contextvars.bind_contextvars(request_id=request_id, user_id=user_id)
logger.info("order_created", order_id=order.id, total=order.total)
```

### Distributed Tracing

Use OpenTelemetry for traces and metrics:

```python
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

FastAPIInstrumentor.instrument_app(app)
SQLAlchemyInstrumentor().instrument(engine=engine)
```

Export to Jaeger, Tempo, Datadog, or any OTLP-compatible backend.

## Database Migrations (Alembic)

- All schema changes go through Alembic migrations — never manual DDL
- Migration naming: `YYYYMMDD_HHMM_<description>.py` or Alembic auto-generated
- Every migration must be reversible (`upgrade()` + `downgrade()`)
- Test migrations against a real database before merging
- Never modify a migration that has been applied to shared environments

## Pagination

Use cursor-based pagination for large datasets, offset for small/admin views:

```python
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
```

- Default page size: 50, max: 200
- Always return `total` count for UI pagination controls
- For high-volume endpoints, prefer cursor-based (`?after=<id>`) over offset

## Security

### CORS

Configure CORS middleware explicitly — never use `allow_origins=["*"]` in production:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # from env
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["*"],
)
```

### Authentication

- Short-lived access tokens (15 min) + refresh tokens (7 days)
- Store refresh tokens in httpOnly cookies (never localStorage)
- Use `python-jose` or `PyJWT` for JWT encode/decode
- Password hashing: `bcrypt` via `passlib` or `bcrypt` library directly
- Define reusable dependency: `CurrentUser = Annotated[User, Depends(get_current_user)]`

### Rate Limiting

- Application-level: `slowapi` for per-endpoint or per-user limits
- Production: prefer rate limiting at reverse proxy / API gateway level (nginx, Kong)
- Always return `Retry-After` header on 429 responses

### Input Validation

- Pydantic models handle request validation automatically
- Use `Field(min_length=..., max_length=..., pattern=...)` for string constraints
- Use `conint(ge=0, le=100)` for numeric bounds
- Never trust path/query params — validate UUIDs via type annotations

## Docker & Deployment

### Dockerfile (multi-stage with uv)

```dockerfile
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src/ src/
RUN uv sync --frozen --no-dev

FROM python:3.14-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv .venv
ENV PATH="/app/.venv/bin:$PATH"
RUN adduser --disabled-password --no-create-home appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Key rules:**

- Use `python:3.14-slim` (not alpine — compiled package issues)
- Multi-stage builds: dependencies cached separately from source
- Run as non-root user
- `--frozen` ensures lockfile is respected
- Never install dev dependencies in production image

### Graceful Shutdown

Handled by the lifespan context manager. On SIGTERM:

1. Uvicorn stops accepting new connections
2. In-flight requests complete (configurable timeout)
3. Post-yield shutdown code runs (close DB pools, flush telemetry)

Use `--timeout-graceful-shutdown` in uvicorn for tuning.

## pyproject.toml Configuration

All project configuration lives in `pyproject.toml` — no `setup.cfg`, `setup.py`, `pytest.ini`, or `.flake8`:

```toml
[project]
name = "myapp"
version = "0.1.0"
requires-python = ">=3.14"

[tool.ruff]
target-version = "py314"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"

[tool.pyright]
include = ["app", "tests"]
pythonVersion = "3.14"
typeCheckingMode = "strict"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = ["integration: marks integration tests", "e2e: marks end-to-end tests"]
```

> **Architecture decisions**: permanent architectural choices live in `.devt/memory/decisions/` (ADR-xxx). Concepts in `.devt/memory/concepts/` (CON-xxx) define mental models. Flows in `.devt/memory/flows/` (FLOW-xxx) document named sequences. Query via `node bin/devt-tools.cjs memory affects <path>` to see what governs a given file.
