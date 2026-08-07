# Internal Task Service

A small HTTP service that owns the canonical list of internal team tasks: create, list (with filter/sort/paginate), fetch, update, and delete. It persists to PostgreSQL through an async SQLAlchemy repository, scales to multiple uvicorn workers (`WEB_CONCURRENCY`), and keeps a swappable repository contract behind an `interfaces.py` port — the Phase-2 move from in-memory SQLite to Postgres touched only the infrastructure adapter, not the domain or application layers.

The locked design lives in [`docs/PRD.md`](docs/PRD.md) (product), [`docs/FRD.md`](docs/FRD.md) (functional), and [`docs/TIS.md`](docs/TIS.md) (technical).

## Why this exists

A small distributed team kept losing track of agreed action items in chat threads and personal to-do lists. There was no single source of truth for "what we said we'd do," which caused duplicates, naming confusion in stand-ups, and no way to filter or prioritize work across the team. The PO asked for "a simple task service. Something internal. Clean. We'll build more on top of it later." This repo is that first iteration.

## What the API looks like

All endpoints are mounted under `/v1`. Open the interactive docs at <http://localhost:8000/docs> for the live schema.

| Method   | Path                         | Purpose                                                     | Success           | Error envelope codes                                                                                                                              |
| -------- | ---------------------------- | ----------------------------------------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `POST`   | `/v1/tasks`                  | Create a task                                               | `201 Created`     | 409 `duplicate_task` / `invalid_transition` / `wip_limit_exceeded`, 422 `validation_error` / `unknown_status` / `read_only_field`                                        |
| `GET`    | `/v1/tasks`                  | List (filter / sort / paginate)                             | `200 OK`          | 422 `validation_error`                                                                                                                            |
| `GET`    | `/v1/tasks/{id}`             | Fetch one task                                              | `200 OK`          | 404 `task_not_found`, 422 `validation_error`                                                                                                      |
| `PUT`    | `/v1/tasks/{id}`             | Replace all mutable fields                                  | `200 OK`          | 403 `transition_forbidden`, 404 `task_not_found`, 409 `duplicate_task` / `invalid_transition` / `wip_limit_exceeded`, 422 `validation_error` / `unknown_status` / `read_only_field`                  |
| `PATCH`  | `/v1/tasks/{id}`             | Update any subset of fields                                 | `200 OK`          | 403 `transition_forbidden`, 404 `task_not_found`, 409 `duplicate_task` / `invalid_transition` / `wip_limit_exceeded`, 422 `validation_error` / `unknown_status` / `read_only_field` / `empty_update` |
| `DELETE` | `/v1/tasks/{id}`             | Delete a task                                               | `204 No Content`  | 404 `task_not_found`, 422 `validation_error`                                                                                                      |
| `GET`    | `/v1/tasks/{id}/transitions` | Legal moves out of the task's state (UI buttons)            | `200 OK`          | 404 `task_not_found`, 422 `validation_error`                                                                                                      |
| `GET`    | `/v1/workflow`               | The active workflow definition                              | `200 OK`          | —                                                                                                                                                 |
| `PUT`    | `/v1/workflow`               | Replace the workflow definition                             | `200 OK`          | 409 `workflow_states_in_use`, 422 `invalid_workflow_definition` / `validation_error`                                                              |
| `GET`    | `/healthz`                   | Liveness — synchronous, no I/O                              | `200 OK`          | —                                                                                                                                                 |
| `GET`    | `/readyz`                    | Readiness — DB round-trip                                   | `200 OK` or `503` | —                                                                                                                                                 |
| `GET`    | `/metrics`                   | Prometheus exposition (ops-only, not in the OpenAPI schema) | `200 OK`          | —                                                                                                                                                 |

Every non-2xx response uses the same envelope: `{"error": {"code", "message", "details", "request_id"}}`. The `code` is machine-readable so consumers can branch without parsing English. A few responses are produced globally rather than per-route: `413 payload_too_large` (body over the size limit) and `504 request_timeout` (handler over the time budget) by request-hardening middleware, and `503 service_unavailable` when the database is unreachable or its connection pool is saturated — a retryable failure.

### Example: create, update, list

```bash
# Create
curl -X POST http://localhost:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "ship task service", "priority": 4}'
# → 201 {"id":"0192b3c4-5d6e-7f80-9a1b-2c3d4e5f6070","title":"ship task service","status":"new","priority":4,...}

# Move to in-progress
curl -X PATCH http://localhost:8000/v1/tasks/0192b3c4-5d6e-7f80-9a1b-2c3d4e5f6070 \
  -H 'Content-Type: application/json' \
  -d '{"status": "in_progress"}'

# List open work, highest priority first
curl 'http://localhost:8000/v1/tasks?status=new&order_by=priority&order_dir=desc&limit=20'

# Duplicate title — 409 with structured error
curl -X POST http://localhost:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -d '{"title": "Ship Task Service", "priority": 1}'
# → 409 {"error":{"code":"duplicate_task","message":"...","details":{"title":"Ship Task Service"},"request_id":"..."}}

# The state machine itself is runtime data — inspect or replace it
curl http://localhost:8000/v1/workflow
# → 200 {"version":1,"created_at":"...","definition":{"states":[...],"transitions":[...]}}

# Which moves are legal for task 1 right now (what a UI renders as buttons)
curl http://localhost:8000/v1/tasks/0192b3c4-5d6e-7f80-9a1b-2c3d4e5f6070/transitions
# → 200 {"task_id":"0192b3c4-5d6e-7f80-9a1b-2c3d4e5f6070","status":"in_progress","transitions":[{"name":"Complete","to":"completed","meta":{}}, ...]}
```

## Approach

The service is built around four design choices, each tied to an objective from PRD §3.

**Feature-first hexagonal layout.** Each feature under `app/services/<feature>/` owns its full vertical slice — `domain/`, `application/`, `infrastructure/`, `api/` — and exposes a single `interfaces.py` ABC for the storage port. This keeps related code together (you change one feature in one folder) while preserving the dependency rule: `api` → `application` → `domain`, and `infrastructure` implements `interfaces.py`. The textbook Cosmic-Python ceremony (separate `ports/`, `Protocol` typing, distinct domain entity apart from the ORM row) is deliberately _not_ used in Phase 1 — see TIS §1 (architecture overview) and §4.1 (ORM-as-domain Decision callout).

**Single domain+ORM entity.** The `Task` SQLModel row _is_ the domain entity (`table=True`). Phase 1 does not split domain and ORM into two classes; the duplication wasn't paying for itself at this scale. If/when a richer domain model arrives (state machines, invariants the ORM can't express), the split happens then.

**Durable event delivery (transactional outbox).** Each mutation writes its events (`TaskCreated`, `TaskUpdated`, `TaskStatusChanged`, `TaskCompleted`, `TaskDeleted`, and the workflows feature's `WorkflowUpdated`) into an `outbox` table **in the same transaction** as the row change — so an event is never lost to a crash between commit and delivery. An in-process relay (`app/core/outbox.py`, started in the lifespan) then delivers each pending event to the `EventBus` listeners **at-least-once**, off the request path so it never blocks the HTTP call, marks it published, and retries failures. Retries carry no backoff, so `OUTBOX_MAX_RETRIES x OUTBOX_POLL_INTERVAL_SECONDS` is the outage a delivery survives (defaults ~5 minutes); past it the row is stamped `dead_lettered_at` and kept for triage — terminal, never re-polled, never pruned. Only delivered rows age out, after `OUTBOX_RETENTION_DAYS` (default 7), deleted in bounded batches. Listeners are idempotent (they dedupe on `event.id`). One listener ships today (structured-log subscriber); notifications / Kafka would land as new listeners, not a mechanism change.

**Workflow as a service.** Task states and transitions are **runtime data**, not code: the active definition (states, entry points, named transitions, open `meta` fields) lives in a versioned DB row managed via `GET/PUT /v1/workflow`, and the tasks service enforces it on every status change — illegal moves 409 with the allowed list, definitions that would strand existing tasks are rejected. A definition can also declare **guards** as `meta`: a transition's `roles` (actor must hold one, else 403 — roles from a provisional `X-Roles` header until auth lands) and a state's `wip_limit` (entering a full state → 409, best-effort). The engine reads them via a `TransitionContext` the service builds per write. The shipped seed is behavior-identical to the original fixed three-state contract, so the default experience is unchanged until someone reshapes the workflow.

**Swappable repository.** `TaskRepositoryInterface` is an ABC, not a `Protocol` — any implementation that forgets a method fails at _instantiation_ time with a clear `TypeError`. Contract tests (`tests/contract/`) are parametrised over every concrete repository, so adding a Postgres adapter in Phase 2 requires zero new test code.

**Other rationale, briefly:**

- **`title_key = title.strip().casefold()`** is the canonical uniqueness column; original `title` is preserved verbatim for display. Duplicate detection goes through `title_key`, never `title`. This is what makes "Fix bug" and " fix BUG" the same task.
- **Single global error handler** converts every `AppError` subclass and every Pydantic `RequestValidationError` into the same envelope. Domain code never builds HTTP responses — `raise DuplicateTaskError(details={"title": …})` is enough. In `dev` mode only, raisers may pass `original_error=` and the envelope's `details.cause` will surface the underlying exception (gated by `settings.expose_stack_traces`); other envs strip it.
- **All timestamps UTC, always.** `datetime.now(UTC)` everywhere; the Docker image sets `TZ=UTC`. Naïve datetimes are a bug, surfaced by pyright and the `ensure_utc` boundary helper.
- **Request-ID middleware** generates a UUIDv4 when `X-Request-ID` is absent, binds it to the structlog context, and echoes it on the response. Every log line in a request carries the same id.
- **Request-hardening middleware** attaches security headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`; HSTS in prod), bounds request body size and handler wall-clock time (enveloped `413` / `504`), and exposes Prometheus metrics at `/metrics`. CORS is config-driven and off by default (empty allow-list) until the Phase 2 SPA lands.
- **Negotiated zstd compression** (`ZstdMiddleware`, installed innermost) compresses buffered responses over 500 bytes with Python 3.14's stdlib `compression.zstd` (PEP 784) when the client sends `Accept-Encoding: zstd`, tagging them `Content-Encoding: zstd` + `Vary: Accept-Encoding`. Streaming, already-encoded, and sub-threshold responses pass through untouched.

## Project layout

The codebase is organised feature-first: each feature under `app/services/<feature>/` is a self-contained vertical slice with its own `domain/`, `application/`, `infrastructure/`, and `api/` layers, plus an `interfaces.py` ABC for the storage port and an `errors.py` for feature-typed exceptions. Cross-cutting concerns live in `app/core/`. Tests are split by what they need (unit lives next to the feature; everything else lives under the top-level `tests/`).

```
app/
├── __init__.py                    # __version__ (single source of truth; hatchling reads here)
├── main.py                        # FastAPI app factory + lifespan + middleware wiring
├── core/                          # Cross-cutting infrastructure — no feature imports here
│   ├── config.py                  # pydantic-settings + APP_ENV behavior matrix
│   ├── constants.py               # Environment / OrderDirection enums + INT64_MAX, list-limit bounds
│   ├── compression.py             # ZstdMiddleware — negotiated zstd response compression (PEP 784)
│   ├── database.py                # Async SQLAlchemy engine + async_sessionmaker (asyncpg); configure/dispose
│   ├── datetime_utils.py          # ensure_utc helper (boundary normaliser)
│   ├── dependencies.py            # Cross-cutting DI: get_session (request AsyncSession)
│   ├── diagnose.py                # /diagnose ops endpoint (dev-gated detail, secret-masked)
│   ├── errors.py                  # ErrorCode enum, AppError hierarchy, global handlers
│   ├── event_bus.py               # In-process EventBus (subscribe/dispatch) + base Event
│   ├── health.py                  # /healthz and /readyz handlers
│   ├── logging.py                 # structlog configuration
│   ├── middleware.py              # Request-ID, security headers, body-size + timeout limits
│   ├── openapi_responses.py       # ErrorEnvelope schema + shared 404 / 409 / 422 response specs
│   └── outbox.py                  # Transactional outbox: OutboxRecord + relay (durable event delivery)
└── services/
    └── tasks/                     # Feature-first vertical slice — full domain/app/infra/api
        ├── domain/                # Task SQLModel (table=True) + 5 domain events + MUTABLE_FIELDS
        ├── application/           # TaskService (use-case orchestration) + DTOs
        ├── infrastructure/        # SQLModelTaskRepository + event listeners
        ├── api/v1/                # FastAPI router (mounted under /v1/tasks)
        ├── interfaces.py          # TaskRepositoryInterface ABC
        ├── constants.py           # TaskSortField StrEnum, field bounds, COMPLETES_META_KEY
        ├── dependencies.py        # Feature DI providers (repository, service, query params)
        ├── errors.py              # DuplicateTaskError, InvalidTransitionError, TaskNotFoundError, EmptyUpdateError, UnknownStatusError
        ├── MODULE.md              # Feature-internal doc: invariants, error-table, conventions
        └── tests/                 # Feature-local unit tests (no FastAPI, no DB)
    └── workflows/                 # Workflow definitions as runtime data (GET/PUT /v1/workflow)
        ├── domain/                # State/Transition value objects + Workflow definition + events
        ├── application/           # WorkflowService (validate + strand guard) + DTOs
        ├── infrastructure/        # Versioned JSON storage + behavior-identical seed + listeners
        ├── api/v1/                # FastAPI router (mounted under /v1/workflow)
        ├── interfaces.py          # WorkflowRepositoryInterface ABC + StoredWorkflow
        ├── serialization.py       # Document boundary — collect-all-errors validation
        ├── errors.py              # WorkflowValidationError, WorkflowStatesInUseError
        ├── dependencies.py        # Feature DI providers (repository, service)
        └── MODULE.md              # Feature-internal doc
tests/
├── conftest.py                    # Test fixtures (in-process app, lifespan, fresh DB)
├── integration/                   # httpx.AsyncClient against in-process FastAPI app
├── contract/                      # Parametrised over every TaskRepositoryInterface impl
├── e2e/                           # Schemathesis property tests (pytest marker: ``e2e``)
└── hurl/                          # 14 black-box scenarios against the running container
docker/                            # Multi-stage Dockerfile + docker-compose.yaml
docs/                              # PRD (product), FRD (functional), TIS (technical)
.github/workflows/                 # CI: pre-commit → pyright → pytest → Hurl
reports/hurl/                      # Generated HTML + JSON reports (gitignored except .gitkeep)
```

### Layered import rules

Enforced by review (not tooling) — see `docs/TIS.md` §1 for the full contract (and §3.1 for the layer-responsibility table):

1. `domain/**` may import stdlib, `pydantic`, `sqlmodel`, `app/core/*`. **No `fastapi`.**
2. `application/**` may import `domain/`, `interfaces.py`, and a sibling feature's `interfaces.py`/`domain/` types. **No `infrastructure/`, no `fastapi`.**
3. `infrastructure/**` may import everything in the feature plus DB helpers from `app/core/`.
4. `api/**` is the only feature-internal place that touches `fastapi`.
5. `app/core/**` must not import from any individual service.

The dependency arrow always points inward: `api → application → domain ← infrastructure (implements interfaces.py)`. Swapping the in-memory store for async Postgres (Phase 2) was contained to `infrastructure/` and `interfaces.py`; `domain/` and `application/` stayed intact, widening only to `async`.

## Assumptions

Carried forward from PRD §10 — these define the operating envelope for Phase 1:

1. **Callers are trusted internal services or developers.** No rate limiting, authentication, captcha, or abuse protection — that arrives in Phase 2 when the service moves beyond the LAN.
2. **Task data is not sensitive, but it is now durable.** The service persists to PostgreSQL (`postgresql+asyncpg://…`); tasks survive process and container restarts. The Phase-1 in-memory SQLite store — where data was lost on restart by design — has been retired.
3. **Multi-worker capable.** The repository is async (async SQLAlchemy over asyncpg) and worker count is set by `WEB_CONCURRENCY` (default 1); Postgres transaction-scoped advisory locks (`pg_advisory_xact_lock`) keep the workflow-vs-status critical section atomic across workers. (Hurl E2E still runs with `--jobs 1`, now only to isolate scenarios that share one database — no longer a storage constraint.)
4. **The team is comfortable with Python 3.14, FastAPI, and `uv`.** No alternative package manager or runtime is supported.

## Setup

### Prerequisites

- Python 3.14+
- [`uv`](https://docs.astral.sh/uv/) (the only supported package manager — do not run `pip` directly)
- Docker + Docker Compose — the `make compose-up` run path and Hurl E2E, and the easiest way to provide the PostgreSQL the app now requires
- Hurl 4+ (only required for `make hurl-e2e`; CI pins **8.0.1** — see `.github/workflows/ci.yaml`)

### Local install

```bash
make install         # uv sync --all-groups + pre-commit hooks
cp .env.example .env # one-time: seed the base config file
```

`make install` pins to `uv.lock` and wires the git pre-commit hooks (ruff, ruff-format, bandit, file hygiene, `uv lock --check`).

`cp .env.example .env` is the **manual** step that gives the app its working defaults. `.env.example` is the only `.env*` file checked into git; copying it to `.env` is what `pydantic-settings` reads on startup. (Per-environment override files like `.env.qa` are optional and explained in [§ Configuration](#configuration).)

### Run it (simplest — full stack in Docker)

The app now requires **PostgreSQL**. `make compose-up` brings up the whole stack —
Postgres, the app, and `alembic upgrade head` — in one healthcheck-gated command:

```bash
make compose-up     # Postgres + app + migrations; app on :8000 (APP_PORT to override)
make compose-logs   # tail logs
make compose-down   # tear down (append `-v` in the compose command to drop the data volume)
```

Then open <http://localhost:8000/docs>, and confirm it's serving:

```bash
curl http://localhost:8000/readyz   # {"status":"ready"} once the DB round-trips
```

### Run the reload dev-server (no app container)

For `uvicorn --reload`, provide a Postgres yourself, apply the schema, then run the server —
the app no longer creates tables (Alembic owns the schema):

```bash
make db-up          # start a host-reachable Postgres on :5432 (idempotent) + apply migrations
make run            # uvicorn --reload on :8000 (override with APP_PORT=9000 make run)
make db-down        # remove it again (its data volume goes too)
```

The default `DATABASE_URL` (in `.env`) expects Postgres on `localhost:5432` with
`taskservice/taskservice/taskservice`, which is exactly what `make db-up` starts. If you already
run Postgres on that port, `db-up` names the container holding it and stops rather than fighting
it — either point `DATABASE_URL` at that instance, or move this one out of the way with
`make db-up DEV_DB_PORT=5433 && make run DEV_DB_PORT=5433`, which carries the override through to
the app as well as the database. Against a database you manage yourself, `make migrate` applies
the schema on its own. (The compose Postgres publishes no ports of its own — it is internal to the
container stack; `db-up` layers `docker/docker-compose.dev.yaml` on top to publish one, under a
separate compose project so an E2E run's `down -v` cannot take your dev data with it.)

## Tests

Tests live at four layers, each chosen to give a _different_ kind of confidence:

| Layer              | Location                         | What it proves                                           | When it runs         |
| ------------------ | -------------------------------- | -------------------------------------------------------- | -------------------- |
| **Unit**           | `app/services/<feature>/tests/`  | Single classes/functions in isolation; no FastAPI, no DB | Every `make test`    |
| **Integration**    | `tests/integration/`             | The HTTP boundary against `httpx.AsyncClient` + ASGI     | Every `make test`    |
| **Contract**       | `tests/contract/`                | Every `TaskRepositoryInterface` impl satisfies the ABC   | Every `make test`    |
| **E2E (Hurl)**     | `tests/hurl/`                    | Black-box HTTP flows against the running container       | `make hurl-e2e` / CI |
| **Property-based** | `tests/e2e/test_schemathesis.py` | Schemathesis fuzzes every documented operation           | `make schemathesis`  |

The split rule for unit vs. integration: _can this test run with only my feature module imported?_ Yes → unit test, lives in `app/services/<feature>/tests/`. No (needs the full FastAPI app, real HTTP, or another feature) → cross-boundary, lives in `tests/`.

```bash
make all                # lint + typecheck + full pytest + schemathesis (coverage gate at 80%)
make test               # full pytest with coverage gate
make test-unit          # feature-local unit tests only — fast, no FastAPI/DB
make test-integration   # in-process FastAPI + Postgres (testcontainers)
make test-contract      # repository ABC conformance — parametrised over every impl
make hurl-e2e           # 14-scenario black-box Hurl suite against the docker-compose container
make schemathesis       # Schemathesis property tests via pytest (ASGI in-process, no container)
```

Run a single pytest:

```bash
uv run pytest -k test_name
uv run pytest tests/integration/services/tasks/test_create_task.py::test_create_returns_201_with_envelope
```

### Hurl E2E scenarios

**What it is.** [Hurl](https://hurl.dev) is a small CLI that runs plain-text `.hurl` files of HTTP requests with first-class support for variable captures, JSONPath assertions, and stateful multi-step flows. We use it as the highest-level (black-box) test layer: scenarios talk to the _running_ container, not the in-process FastAPI app, so the Docker image, lifespan, healthcheck, and middleware stack are all exercised end-to-end.

**Why Hurl on top of pytest.** Integration tests (pytest + `httpx.AsyncClient`) cover correctness _inside_ the Python process; they bypass the Docker image, the uvicorn process model, and any container-side glue. Hurl runs the same image that ships to production. The two layers catch different things — pytest catches logic bugs, Hurl catches packaging / config / runtime bugs.

**Run the full suite (recommended path).** Brings the container up, runs every `tests/hurl/*.hurl` file sequentially, writes HTML + JSON reports, then tears the container down — even on failure (trap on `EXIT`):

```bash
make hurl-e2e
# → reports/hurl/index.html  (per-request clickable view)
# → reports/hurl/report.json (machine-readable)
```

`--jobs 1` is hard-coded in the target so scenarios that share one database run sequentially and don't race on each other's rows. (Before Phase 2 this was also a storage constraint — in-memory SQLite + `StaticPool` serialised on one connection — but Postgres now handles concurrent connections, so scenario isolation is the only remaining reason.)

**Run a single scenario standalone.** Useful while authoring a new scenario or debugging an assertion failure. Bring the container up yourself, then point Hurl at one file:

```bash
make compose-up                                     # 1. start the container (healthcheck-gated)
hurl --test --verbose \
     --variable base_url=http://localhost:8000 \
     tests/hurl/task_full_flow.hurl                 # 2. run just this scenario
make compose-down                                   # 3. tear down when done
```

Use `--very-verbose` for full request/response bodies — invaluable when an `[Asserts]` line fails and you need to see what the server actually sent back.

**The 14 scenarios in `tests/hurl/`.**

| Scenario                             | What it pins down                                                                                                                                                                                                                                                 |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `aaa_sort_priority.hurl`             | Runs first (empty DB); priority sort default + ASC/DESC + tie-break by `created_at` + invalid `order_by` / `order_dir` rejections                                                                                                                                 |
| `healthz.hurl`                       | `GET /healthz` returns 200 (no I/O — process is alive)                                                                                                                                                                                                            |
| `readyz.hurl`                        | `GET /readyz` does a real DB round-trip and returns 200                                                                                                                                                                                                           |
| `request_id_propagation.hurl`        | `X-Request-ID` echoed when caller sends one; generated when absent                                                                                                                                                                                                |
| `task_create.hurl`                   | Happy-path POST                                                                                                                                                                                                                                                   |
| `task_create_validation_errors.hurl` | Each invalid-input shape → 422 with the right code                                                                                                                                                                                                                |
| `task_create_duplicate_title.hurl`   | Case-insensitive + trimmed duplicate detection on CREATE                                                                                                                                                                                                          |
| `task_not_found.hurl`                | 404 envelope shape on GET / PATCH / PUT / DELETE of a missing id                                                                                                                                                                                                  |
| `task_patch_partial.hurl`            | PATCH partial-update semantics; `empty_update` on `{}`                                                                                                                                                                                                            |
| `task_put_full_replace.hurl`         | PUT full-replace semantics                                                                                                                                                                                                                                        |
| `task_lifecycle.hurl`                | One task: `new → in_progress → completed → delete → 404`                                                                                                                                                                                                          |
| `task_list_filter_sort.hurl`         | Sorting, status filter, pagination, limit-validation                                                                                                                                                                                                              |
| `task_full_flow.hurl`                | Multi-task narrative: 4 creates, dup-rejection on create + rename, PATCH/PUT/DELETE, multi-value status filter, error envelopes mid-flow, cleanup                                                                                                                 |
| `zzz_workflow_admin.hurl`            | Workflow admin + enforcement: seeded GET → invalid PUT (422, all errors at once) → strand guard (409) → restrictive PUT → illegal PATCH (409) → transitions view → legal path to `completed` → guard install → role guard (403 without `X-Roles`, 200 with) → WIP limit (409). Runs last (`zzz_`) since its definition governs later-created tasks |

**Authoring conventions** for new `.hurl` files (so they coexist under `--jobs 1` against the shared Postgres database):

- Use a unique title prefix (e.g. `"hurl flow alpha"`, `"hurl list L1"`) so other scenarios' rows can't collide with yours.
- Assert presence with `jsonpath "$.items[?(@.title=='…')]" exists` / `not exists` rather than `$.total == N` — other scenarios' rows pad the total count unpredictably.
- Capture ids once with `[Captures] task_id: jsonpath "$.id"`, then reuse `{{task_id}}` across follow-up requests in the same file.
- Use `{{base_url}}` for the host so the same file works against a local container and against any future remote env.
- If a scenario _creates_ rows it doesn't need to leave behind, `DELETE` them at the end as hygiene.

## Configuration

`pydantic-settings` resolves settings from **three sources, in increasing precedence**:

1. `.env` — base values, copied from `.env.example` during setup.
2. `.env.<APP_ENV>` — optional overrides for the active environment (e.g. `.env.qa`). Layered _on top of_ `.env`, not instead of it.
3. **Process environment variables** — always win over both files. This is what k8s `env:` blocks and CI manifests use.

`APP_ENV ∈ {dev, test, qa, prod}` and defaults to `dev`.

### Per-env behavior matrix

`APP_ENV` also drives three runtime knobs via `app/core/config.py` (not just file selection):

| `APP_ENV` | Default `LOG_LEVEL` | JSON logs             | Stack traces in error responses |
| --------- | ------------------- | --------------------- | ------------------------------- |
| `dev`     | `DEBUG`             | no (console renderer) | yes                             |
| `test`    | `WARNING`           | no                    | no                              |
| `qa`      | `INFO`              | yes                   | no                              |
| `prod`    | `INFO`              | yes                   | no                              |

In `dev`, the error envelope's `details.cause` carries the underlying exception (`"<ExceptionType>: <message>"`) whenever the raiser passes `original_error=`. Other envs strip it. This is the runtime form of "stack traces in error responses" for Phase 1; full Python tracebacks are not exposed.

### Examples

```bash
# Switch the active per-env file. .env still loads as the base layer.
APP_ENV=test uv run pytest
APP_ENV=qa   make run

# One-off override of a single setting (process env var beats both files).
APP_ENV=qa LOG_LEVEL=DEBUG uv run uvicorn app.main:app
```

`.env.example` is the only `.env*` file tracked in git. `.env` and any `.env.<APP_ENV>` are gitignored and `.dockerignore`d — secrets stay on the developer machine / in the orchestrator.

## Limitations & roadmap

- **Durable storage** — ✅ resolved in Phase 2: the service persists to PostgreSQL (async SQLAlchemy + Alembic migrations), so data survives restarts. Phase 1's in-memory SQLite lost data on restart by design.
- **No auth / authz / rate limits** — the service assumes trusted callers on a private network.
- **Multi-worker** — ✅ resolved in Phase 2: `WEB_CONCURRENCY` drives `uvicorn --workers`, made safe by Postgres advisory-lock guards.

**Phase 2 (in progress):** shipped a production-hardening slice — security headers, request size/time limits, config-driven CORS, a Prometheus `/metrics` endpoint, CI supply-chain scanning (Dependabot, Trivy, `pip-audit`), and Schemathesis gated in CI — followed by a durability slice: **PostgreSQL + async repository**, **Alembic migrations**, **UUIDv7 IDs**, **Python 3.14**, **`WEB_CONCURRENCY` multi-worker** (advisory-lock-guarded), and **negotiated zstd response compression**; then a delivery-and-governance slice: a **durable transactional outbox** (events staged in the write's transaction, relayed at-least-once, dead-lettered on exhaustion) and **workflow guards** (`meta`-declared role guards + WIP limits). Still ahead: authentication, rate limiting, and real event sinks (Kafka / notifications) — which land as new outbox listeners, not a mechanism change. The application and domain layers stayed untouched; only `infrastructure/` and `interfaces.py` widened.

## Project tooling

`uv` manages everything. `make help` lists every target. Common direct invocations:

```bash
uv run uvicorn app.main:app --reload   # dev server
uv run pytest -k some_test              # single test
uv run ruff check . && uv run pyright   # lint + typecheck
```

Pre-commit hooks wire automatically on `make install` (ruff, ruff-format, bandit, file hygiene, `uv lock --check`).
