# Internal Task Service

A small HTTP service that owns the canonical list of internal team tasks: create, list (with filter/sort/paginate), fetch, update, and delete. Phase 1 ships as a single uvicorn worker with in-memory SQLite, structured logging, and a swappable repository contract so Phase 2 can move to Postgres without touching the domain or application layers.

The locked design lives in [`docs/PRD.md`](docs/PRD.md) (product), [`docs/FRD.md`](docs/FRD.md) (functional), and [`docs/TIS.md`](docs/TIS.md) (technical).

## Why this exists

A small distributed team kept losing track of agreed action items in chat threads and personal to-do lists. There was no single source of truth for "what we said we'd do," which caused duplicates, naming confusion in stand-ups, and no way to filter or prioritize work across the team. The PO asked for "a simple task service. Something internal. Clean. We'll build more on top of it later." This repo is that first iteration.

### Use cases

| Persona               | Story                                                                            |
| --------------------- | -------------------------------------------------------------------------------- |
| **Developer**         | Create a task right after a stand-up via `POST /v1/tasks`; later script bulk imports from CI |
| **Developer**         | List open work filtered by `status=new`, sorted by `priority`, paginated by `offset/limit` |
| **Developer**         | PATCH a task to flip status (`new → in_progress → completed`) without resending the title |
| **Product Owner**     | Be prevented from creating duplicate titles (case-insensitive, trimmed)         |
| **On-call engineer**  | Probe `/healthz` / `/readyz`, follow a request across logs via `X-Request-ID`   |
| **Systems architect** | Swap the SQLite repository for Postgres in Phase 2 without rewriting domain/application code |

## What the API looks like

All endpoints are mounted under `/v1`. Open the interactive docs at <http://localhost:8000/docs> for the live schema.

| Method   | Path             | Purpose                              | Success                   | Error envelope codes                                |
| -------- | ---------------- | ------------------------------------ | ------------------------- | --------------------------------------------------- |
| `POST`   | `/v1/tasks`      | Create a task                        | `201 Created`             | 409 `duplicate_task`, 422 `validation_error` / `read_only_field` |
| `GET`    | `/v1/tasks`      | List (filter / sort / paginate)      | `200 OK`                  | 422 `validation_error`                              |
| `GET`    | `/v1/tasks/{id}` | Fetch one task                       | `200 OK`                  | 404 `task_not_found`                                |
| `PUT`    | `/v1/tasks/{id}` | Replace all mutable fields           | `200 OK`                  | 404, 409, 422                                       |
| `PATCH`  | `/v1/tasks/{id}` | Update any subset of fields          | `200 OK`                  | 404, 409, 422 (incl. `empty_update`)                |
| `DELETE` | `/v1/tasks/{id}` | Delete a task                        | `204 No Content`          | 404                                                 |
| `GET`    | `/healthz`       | Liveness — synchronous, no I/O       | `200 OK`                  | —                                                   |
| `GET`    | `/readyz`        | Readiness — DB round-trip            | `200 OK` or `503`         | —                                                   |

Every non-2xx response uses the same envelope: `{"error": {"code", "message", "details", "request_id"}}`. The `code` is machine-readable so consumers can branch without parsing English.

### Example: create, update, list

```bash
# Create
curl -X POST http://localhost:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "ship task service", "priority": 4}'
# → 201 {"id":1,"title":"ship task service","status":"new","priority":4,...}

# Move to in-progress
curl -X PATCH http://localhost:8000/v1/tasks/1 \
  -H 'Content-Type: application/json' \
  -d '{"status": "in_progress"}'

# List open work, highest priority first
curl 'http://localhost:8000/v1/tasks?status=new&order_by=priority&order_dir=desc&limit=20'

# Duplicate title — 409 with structured error
curl -X POST http://localhost:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "Ship Task Service", "priority": 1}'
# → 409 {"error":{"code":"duplicate_task","message":"...","details":{"title":"Ship Task Service"},"request_id":"..."}}
```

## Approach

The service is built around four design choices, each tied to an objective from PRD §3.

**Feature-first hexagonal layout.** Each feature under `app/services/<feature>/` owns its full vertical slice — `domain/`, `application/`, `infrastructure/`, `api/` — and exposes a single `interfaces.py` ABC for the storage port. This keeps related code together (you change one feature in one folder) while preserving the dependency rule: `api` → `application` → `domain`, and `infrastructure` implements `interfaces.py`. The textbook Cosmic-Python ceremony (separate `ports/`, `Protocol` typing, distinct domain entity apart from the ORM row) is deliberately *not* used in Phase 1 — TIS §3.1 explains the trade-off.

**Single domain+ORM entity.** The `Task` SQLModel row *is* the domain entity (`table=True`). Phase 1 does not split domain and ORM into two classes; the duplication wasn't paying for itself at this scale. If/when a richer domain model arrives (state machines, invariants the ORM can't express), the split happens then.

**Five-event domain bus.** The application service publishes `TaskCreated`, `TaskUpdated`, `TaskStatusChanged`, `TaskCompleted`, `TaskDeleted` after each mutation via `EventBus.publish(event, background_tasks)`. Listeners run through FastAPI `BackgroundTasks` so they execute *post-commit, pre-response* without blocking the HTTP call. Phase 1 ships one listener (structured-log subscriber); the bus is the seam where notifications / outbox / Kafka would land in Phase 2.

**Swappable repository.** `TaskRepositoryInterface` is an ABC, not a `Protocol` — any implementation that forgets a method fails at *instantiation* time with a clear `TypeError`. Contract tests (`tests/contract/`) are parametrised over every concrete repository, so adding a Postgres adapter in Phase 2 requires zero new test code.

**Other rationale, briefly:**

- **`title_key = title.strip().casefold()`** is the canonical uniqueness column; original `title` is preserved verbatim for display. Duplicate detection goes through `title_key`, never `title`. This is what makes "Fix bug" and "  fix BUG" the same task.
- **Single global error handler** converts every `AppError` subclass and every Pydantic `RequestValidationError` into the same envelope. Domain code never builds HTTP responses — `raise DuplicateTaskError(details={"title": …})` is enough.
- **All timestamps UTC, always.** `datetime.now(UTC)` everywhere; the Docker image sets `TZ=UTC`. Naïve datetimes are a bug, surfaced by mypy and the `ensure_utc` boundary helper.
- **Request-ID middleware** generates a UUIDv4 when `X-Request-ID` is absent, binds it to the structlog context, and echoes it on the response. Every log line in a request carries the same id.

## Project layout

The codebase is organised feature-first: each feature under `app/services/<feature>/` is a self-contained vertical slice with its own `domain/`, `application/`, `infrastructure/`, and `api/` layers, plus an `interfaces.py` ABC for the storage port and an `errors.py` for feature-typed exceptions. Cross-cutting concerns live in `app/core/`. Tests are split by what they need (unit lives next to the feature; everything else lives under the top-level `tests/`).

```
app/
├── core/                          # Cross-cutting: config, constants, errors, event_bus,
│                                  #   logging, middleware, datetime_utils,
│                                  #   openapi_responses, dependencies, health, database
├── main.py                        # FastAPI app factory + lifespan + middleware wiring
└── services/tasks/
    ├── domain/                    # Task SQLModel (table=True) + 5 domain events
    ├── application/               # TaskService (use-case orchestration) + DTOs
    ├── infrastructure/            # SQLModelTaskRepository + event listeners
    ├── api/v1/                    # FastAPI router (mounted under /v1/tasks)
    ├── interfaces.py              # TaskRepositoryInterface ABC + MUTABLE_FIELDS frozenset
    ├── constants.py               # Status / TaskSortField StrEnums + field bounds
    ├── dependencies.py            # Feature DI providers (repository, service, query params)
    ├── errors.py                  # DuplicateTaskError, TaskNotFoundError, EmptyUpdateError, …
    └── tests/                     # Feature-local unit tests (no FastAPI, no DB)
tests/
├── conftest.py                    # Test fixtures (in-process app, lifespan, fresh DB)
├── integration/                   # httpx.AsyncClient against in-process FastAPI app
├── contract/                      # Parametrised over every TaskRepositoryInterface impl
├── e2e/                           # Opt-in Schemathesis property tests (marker: ``e2e``)
└── hurl/                          # 11 black-box scenarios against the running container
docker/                            # Multi-stage Dockerfile + docker-compose.yaml
docs/                              # PRD (product), FRD (functional), TIS (technical)
.github/workflows/                 # CI: pre-commit → mypy → pytest → Hurl → docker build
reports/hurl/                      # Generated HTML + JSON reports (gitignored except .gitkeep)
```

### Layered import rules

Enforced by review (not tooling) — see `docs/TIS.md` §2 for the full contract:

1. `domain/**` may import stdlib, `pydantic`, `sqlmodel`, `app/core/*`. **No `fastapi`.**
2. `application/**` may import `domain/` and `interfaces.py`. **No `infrastructure/`, no `fastapi`.**
3. `infrastructure/**` may import everything in the feature plus DB helpers from `app/core/`.
4. `api/**` is the only feature-internal place that touches `fastapi`.
5. `app/core/**` must not import from any individual service.

The dependency arrow always points inward: `api → application → domain ← infrastructure (implements interfaces.py)`. Swapping the repository for Postgres in Phase 2 means editing `infrastructure/` + `interfaces.py` only — `domain/`, `application/`, and `api/` stay untouched.

## Assumptions

Carried forward from PRD §10 — these define the operating envelope for Phase 1:

1. **Callers are trusted internal services or developers.** No rate limiting, authentication, captcha, or abuse protection — that arrives in Phase 2 when the service moves beyond the LAN.
2. **Task data is not sensitive and data loss on restart is acceptable.** Phase 1 uses in-memory SQLite (`sqlite+pysqlite:///:memory:`); tasks disappear when the process or container restarts. Intentional.
3. **Single instance, single uvicorn worker.** The repository is synchronous; concurrency beyond one worker is out of scope. (Hurl E2E tests must run with `--jobs 1` for the same reason — `StaticPool` serialises on a single shared connection.)
4. **The team is comfortable with Python 3.13, FastAPI, and `uv`.** No alternative package manager or runtime is supported.

## Setup

### Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) (the only supported package manager — do not run `pip` directly)
- Docker + Docker Compose (only required for the container path and Hurl E2E)
- Hurl 4+ (only required for `make hurl-e2e`)

### Local install

```bash
make install        # uv sync --all-groups + pre-commit hooks
```

This pins to `uv.lock` and wires the git pre-commit hooks (ruff, ruff-format, bandit, file hygiene, `uv lock --check`).

### Run locally (no Docker)

```bash
make run            # uvicorn --reload on :8000 (override with APP_PORT=9000 make run)
```

Open <http://localhost:8000/docs> for the OpenAPI UI.

### Run in Docker

```bash
make compose-up     # build image, start container, wait for healthcheck
make compose-logs   # tail logs
make compose-down   # tear down
```

A fresh checkout to a running service is one command — `make compose-up` or `make run` — with no further setup beyond `uv` and Docker being installed.

## Tests

The split rule: *can this test run with only my feature module imported?* Yes → unit test, lives in `app/services/<feature>/tests/`. No (needs the full FastAPI app, real HTTP, or another feature) → cross-boundary, lives in `tests/`.

```bash
make all                # lint + typecheck + full pytest suite (~70 tests, 95% coverage gate at 80%)
make test               # full pytest with coverage gate
make test-unit          # feature-local unit tests only — fast, no FastAPI/DB
make test-integration   # in-process FastAPI + SQLite :memory:
make test-contract      # repository ABC conformance — parametrised over every impl
make hurl-e2e           # 11-scenario black-box Hurl suite against the docker-compose container
make schemathesis       # opt-in Schemathesis property tests via pytest (ASGI in-process, no container)
```

`hurl-e2e` brings up the compose service, runs `hurl --test --jobs 1 …`, and tears it down — even on failure (trap on EXIT). `--jobs 1` is mandatory because in-memory SQLite + `StaticPool` serialises on a single shared connection.

Run a single test:

```bash
uv run pytest -k test_name
uv run pytest tests/integration/services/tasks/test_create_task.py::test_create_201
```

## Configuration

`pydantic-settings` selects a per-environment file: `.env.<APP_ENV>`. `APP_ENV ∈ {dev, test, qa, prod}`, defaults to `dev`. Process env vars **override** file contents (so k8s/CI win).

| `APP_ENV` | Default `LOG_LEVEL` | JSON logs              | Stack traces in error responses |
| --------- | ------------------- | ---------------------- | ------------------------------- |
| `dev`     | `DEBUG`             | no (console renderer)  | yes                             |
| `test`    | `WARNING`           | no                     | no                              |
| `qa`      | `INFO`              | yes                    | no                              |
| `prod`    | `INFO`              | yes                    | no                              |

Override config inline:

```bash
APP_ENV=qa LOG_LEVEL=DEBUG uv run uvicorn app.main:app
```

`.env.example` is the only `.env.*` checked in. Per-env files are gitignored; `.dockerignore` keeps them out of the image.

## Limitations & roadmap

- **In-memory data loss on restart** — the most visible Phase 1 limitation. Acceptable for the internal MVP; Phase 2 swaps in Postgres.
- **No auth / authz / rate limits** — the service assumes trusted callers on a private network.
- **Single worker** — multi-worker deployment is a Phase 2 concern.

**Phase 2 (planned):** Postgres + async repository, authentication, multi-worker, mandatory Schemathesis property tests, optional event sinks (outbox / Kafka). The application and domain layers stay untouched; only `infrastructure/` and `interfaces.py` widen.

## Project tooling

`uv` manages everything. `make help` lists every target. Common direct invocations:

```bash
uv run uvicorn app.main:app --reload   # dev server
uv run pytest -k some_test              # single test
uv run ruff check . && uv run mypy      # lint + typecheck
```

Pre-commit hooks wire automatically on `make install` (ruff, ruff-format, bandit, file hygiene, `uv lock --check`).
