# 🏛️ Technical Implementation Specification (TIS)

**Project:** Internal Task Service
**Document Version:** 1.1
**Companion to:** `docs/PRD.md`, `docs/FRD.md`

> **Scope.** This document captures the _how_ — code shape, layer rules, patterns, infrastructure mechanics, and trade-offs. The _what_ (API contracts, error codes, events, config matrix) lives in `docs/FRD.md`. This document assumes FRD has been read.
>
> **Callout conventions:**
>
> - **`> Implements:`** — section implements one or more FRD clauses; the linked clauses are the source of truth.
> - **`> Pure design — no FRD clause.`** — section is implementation-only; no contract to defer to.
> - **`> Decision.`** — accepted trade-off, usually a Phase 1 / Phase 2 split.
> - **`> 🔒 Internal contract.`** — between-layer agreement that future code MUST honour. Not an API contract, so it lives here rather than in FRD.

---

## 1. Architecture Overview

> **Implements:** FRD §1 (Architectural Standards) — this section captures the variant chosen and the layered import rules.

The service follows **simplified Hexagonal Architecture (feature-first)** — each feature owns its full stack (`api/`, `application/`, `domain/`, `infrastructure/`) and exposes an explicit `interfaces.py` ABC for swappable storage. Substitutability and framework isolation are preserved; the ceremony of strict Cosmic-Python hex (separate `ports/` subfolder, Protocol typing, dedicated domain entity class apart from the SQLModel row, CI-enforced import boundaries) is dropped because it is not earned at this scale.

```
                                 ┌──────────────────────────┐
                                 │       Inbound (HTTP)     │
                                 │   app/services/tasks/api │
                                 │   FastAPI router + DTOs  │
                                 └────────────┬─────────────┘
                                              │ calls
                                              ▼
       ┌──────────────────────────┐    ┌──────────────────────┐
       │  interfaces.py           │    │   application/       │
       │  (ABC contracts)         │◄───┤   TaskService        │
       └────────────┬─────────────┘    └─────────┬────────────┘
                    ▲                            │ depends on
                    │ implements                 ▼
       ┌────────────┴─────────────┐    ┌──────────────────────┐
       │      infrastructure/     │    │       domain/        │
       │  SQLModelTaskRepository  │    │ Task (SQLModel +     │
       │  + listeners.py          │    │ table=True)          │
       │                          │    │ Status enum, events  │
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
│           ├── constants.py          # Status enum, TaskSortField, field bounds
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

## 3. Applied Architecture & Design Patterns

> **Pure design — no FRD clause.** Pattern selection is implementation; FRD does not (and should not) prescribe patterns.

The implementation rests on a small set of explicitly chosen patterns. Each one solves a named problem; nothing is applied for ceremony.

| Pattern                                                               | Where it lives                                                                                              | What it buys                                                                                                                         |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Hexagonal Architecture (Ports & Adapters)** — feature-first variant | Whole feature tree under `app/services/tasks/`                                                              | Substitutable storage, framework isolation, test pyramid                                                                             |
| **Repository Pattern** with **ABC-as-Port**                           | `interfaces.py::TaskRepositoryInterface` + `infrastructure/repository.py`                                   | Application depends on a contract, not an ORM; Postgres adapter in Phase 2 needs zero domain churn                                   |
| **Application Service / Use-Case Object**                             | `application/service.py::TaskService`                                                                       | All event-firing rules in one place; routes stay thin                                                                                |
| **Domain Events** + **Publish/Subscribe Bus**                         | `domain/events.py` + `core/event_bus.py`                                                                    | Side-effects (logs, future notifications) are append-only — new listener, no service edit                                            |
| **Background Tasks** for post-commit fan-out                          | `EventBus.publish(event, background_tasks)`                                                                 | Events fire _after_ the DB commit and _before_ the HTTP response returns; listeners never block the caller                           |
| **Snapshot pattern** for event payloads                               | `Task.snapshot()`                                                                                           | Pre/post-mutation values are captured as detached copies, immune to later session mutations                                          |
| **Single Global Exception Handler / Error Envelope**                  | `core/errors.py::register_exception_handlers`                                                               | Domain code raises typed exceptions; HTTP shape is owned by one handler, schema is uniform                                           |
| **Factory Method**                                                    | `Task.from_input()`, `app.main::create_app()`                                                               | Object construction owns invariants; the app's wiring is reproducible and testable                                                   |
| **Dependency Injection** (Annotated style)                            | FastAPI `Annotated[X, Depends(...)]` aliases in `core/dependencies.py` and each feature's `dependencies.py` | Wiring is declared at the type level; swapping a collaborator means swapping one alias                                               |
| **DTO at the API boundary**                                           | `application/dto.py` (Pydantic V2 models with `extra="forbid"`)                                             | Read-only fields rejected by the framework, not by hand-rolled validators                                                            |
| **Reusable Annotated types**                                          | `NonBlankTitle = Annotated[str, Field(...), AfterValidator(...)]`                                           | Title bounds and the blank-rejection rule travel together; both DTOs reuse them by reference                                         |
| **StrEnum for closed string sets**                                    | `Status`, `TaskSortField`, `OrderDirection`, `Environment`, `ErrorCode`                                     | Wire format = symbol value; no `if status_str == "completed"` magic strings anywhere                                                 |
| **Single Source of Truth for bounds**                                 | `app/services/tasks/constants.py` (`Final[int]` scalars + StrEnums)                                         | DTO validation and SQLModel column constraints share one definition; can't drift                                                     |
| **Middleware for request-scoped context**                             | `core/middleware.py::RequestIDMiddleware`                                                                   | UUIDv4 per request, bound to structlog context vars, echoed on the response — all in one place                                       |
| **Lifespan-managed app factory**                                      | `app.main::lifespan` + `create_app()`                                                                       | Startup wires logging, schema, event bus, listeners; ASGI test clients can reuse the same factory                                    |
| **Operational split: liveness vs readiness**                          | `core/health.py`: `/healthz` (no I/O) vs `/readyz` (DB round-trip)                                          | Orchestrator routes traffic on `/readyz`; `/healthz` proves the process is alive without false-positive failures during DB reconnect |

### 3.1 Layer responsibilities

Each layer answers exactly one question. Imports always flow inward toward `domain/`.

| Layer              | Module                           | Answers                                                                     | May import                                           | Must NOT import                      |
| ------------------ | -------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------- | ------------------------------------ |
| **Domain**         | `services/tasks/domain/`         | "What is a Task? What events exist?"                                        | stdlib, `pydantic`, `sqlmodel`, `app.core.*`         | `fastapi`                            |
| **Interfaces**     | `services/tasks/interfaces.py`   | "What can the application ask of storage?"                                  | `domain/`                                            | `infrastructure/`, `fastapi`         |
| **Application**    | `services/tasks/application/`    | "How does a use-case run end-to-end?"                                       | `domain/`, `interfaces.py`                           | `infrastructure/`, `fastapi`         |
| **Infrastructure** | `services/tasks/infrastructure/` | "How does this contract talk to SQLModel / logs?"                           | Anything in the feature + DB helpers from `app.core` | —                                    |
| **API**            | `services/tasks/api/`            | "How does HTTP map to a use-case?"                                          | `application/`, `dependencies.py`                    | Directly into `infrastructure/`      |
| **Core**           | `app/core/`                      | Cross-cutting: config, errors, bus, logging, middleware, health, DB session | stdlib + third-party                                 | Any individual `services/<feature>/` |

The dependency rule is enforced by review (not import-linter). The single feature in Phase 1 keeps it tractable; if a second feature lands, automated boundary checks become worth their weight.

---

## 4. Domain Layer

**Purpose.** Hold the business rules and data shapes the rest of the system orbits around. Nothing here depends on FastAPI, the database driver, or a specific adapter — only Python, Pydantic, and SQLModel field declarations.

### 4.1 `Task` entity

> **Implements:** FRD §2.1 (entity fields and invariants), §2.4 (timezone, title uniqueness).
> **Decisions captured here:** ORM-as-domain dual-use; `Final[int]` bounds placement; `from_input` / `snapshot` factories.

> **Decision.** Phase 1 deliberately does not split a separate "pure domain" class from the ORM row. The `Task` SQLModel row **is** the domain entity (`table=True`). The dual-use simplifies the codebase by ~30% with no observable cost at this scale. Phase 2 may split them if a richer state-machine or invariants the ORM can't express make the duplication earn its keep.

**Where the design lives** (the _what_ is in FRD §2.1):

- Bounds (`title` length, `priority` range, `description` ceiling) live as `Final[int]` constants in `services/tasks/constants.py` and are imported by both the entity _and_ the DTOs — one definition, no drift.
- `title_key = title.strip().casefold()` is the indexed UNIQUE column; `title` stays verbatim for display.
- `created_at` is server-generated via `default_factory=lambda: datetime.now(UTC)`; `extra="forbid"` on inbound DTOs rejects it at the framework boundary, and the global handler converts that to `read_only_field`. No hand-rolled validators.
- Two factory methods sit next to the entity:
  - `Task.from_input(...)` builds a new row, applying `clean_title()` to enforce the title invariants — this is the _only_ way the repository's `add()` constructs a Task.
  - `Task.snapshot()` returns a detached copy (`Task.model_validate(self.model_dump())`) used by the repository to capture pre/post-mutation state for events. Centralising it on the entity eliminated three inline `model_validate(model_dump())` call sites.

> **🔒 Internal contract.** Any code path that needs a frozen pre/post-mutation `Task` value (events, audit) MUST call `Task.snapshot()`. Direct `model_validate(model_dump())` calls are forbidden — they bypass the centralisation guarantee.

### 4.2 `Status` enum and sort fields

> **Implements:** FRD §2.2 (`Status` wire format), §2.3 (status transitions: any→any in Phase 1), §3.3 (`?order_by` allowed values).

`Status` is a `StrEnum` with values `new`, `in_progress`, `completed` — the value _is_ the wire format, so no separate serialisation is required. `TaskSortField` is the same idea for `?order_by=`: a closed set of allowed column names. Both eliminate any string-comparison branching elsewhere in the code.

### 4.3 Domain events

> **Implements:** FRD §5.1 (event catalogue, fire conditions, payload shapes).

The five `Task*` events are `pydantic.BaseModel` subclasses inheriting from `core.event_bus.Event` (which adds `id: UUID` and `occurred_at: datetime`).

`TaskCompleted` is a _convenience event_: listeners that only care about completion (Slack notifier, metrics counter) subscribe to it directly rather than filtering `TaskStatusChanged` payloads. `TaskUpdated` is the catch-all hook for audit / cache-invalidation listeners. This split (one event per intent) is the design choice; FRD §5.1 owns _which_ events fire and _when_.

### 4.4 Feature-level errors

> **Implements:** FRD §4 (error code list, HTTP mapping, envelope rules).

`services/tasks/errors.py` defines `DuplicateTaskError`, `TaskNotFoundError`, `EmptyUpdateError`. Each one subclasses a base class from `app/core/errors.py` (`ConflictError`, `NotFoundError`, `ValidationError`) and pins its `error_code` and default `detail`. Domain code raises these by type; the global handler (§8.1) translates them into the standard envelope. **Never inherit from plain `Exception`** in feature code — that bypasses the handler and returns a 500 with no envelope.

`ReadOnlyFieldError` lives in `app/core/errors.py` rather than the feature, because server-owned-field rejection (`id`, `created_at`) is a framework-level concern: every feature with server-managed fields routes through the same global validation handler (§8.1), which instantiates `ReadOnlyFieldError` itself — feature code does not raise it.

---

## 5. Repository Interface (Storage Port)

> **Pure design — no FRD clause.** The repository is internal infrastructure; FRD §3 specifies API behaviour, not storage shape.

**Purpose.** Define what the application can ask of storage _without_ committing to a particular adapter. The application layer depends on this ABC; concrete adapters depend on it implicitly by inheriting.

**Why `ABC + @abstractmethod` over `Protocol`.** A `Protocol` is structurally typed; a missing method only fails when first called (`AttributeError` at runtime). An ABC fails at _instantiation_ time with a clear `TypeError: Can't instantiate abstract class ... with abstract methods ...`. The earlier feedback loop is worth the slight rigidity for a small contract.

**The contract.** Six methods: `add`, `get`, `list`, `replace`, `patch`, `delete`. The signatures encode three deliberate decisions:

> **🔒 Internal contract.** `replace()` and `patch()` MUST return `tuple[Task, Task]` — `(pre_mutation_snapshot, updated_row)`. The service layer relies on this single-fetch contract to avoid a redundant `get()` for pre-state. Postgres adapters that don't share SQLAlchemy's identity-map benefit from this directly.

1. **`replace()` and `patch()` return `tuple[Task, Task]`** — see the internal contract above.
2. **`delete()` returns the deleted `Task`** (a snapshot) — the service needs it to publish `TaskDeleted` with the row that no longer exists in the database.
3. **`get()` raises `TaskNotFoundError`** — the absence is a domain event, not a sentinel return. Callers can let it propagate to the global handler.

> **🔒 Internal contract.** `MUTABLE_FIELDS = frozenset({"title", "description", "status", "priority"})` MUST live in `domain/models.py` next to `Task`. The service consumes it for change-detection; `Task.patch()` consumes it to validate the patch dict. The repository deliberately stays out of mutability enforcement — that's a domain concern. Duplicating the set anywhere would let the two consumers drift.

---

## 6. Application Layer

**Purpose.** Orchestrate use-cases. Each public method on `TaskService` is one use-case from FRD §3; the service decides which events fire, in what order, and whether the patch was actually a no-op.

### 6.1 `TaskService`

> **Implements:** FRD §3 (use-case → endpoint mapping), §5.1 (event-firing rules — enforced as service-level unit tests).

Six methods (`create`, `get`, `list`, `replace`, `patch`, `delete`), all `async def` — CLAUDE.md mandates async at the service boundary. Two collaborators are injected at construction (constructor injection): a `TaskRepositoryInterface` and an `EventBus`. The service does not know whether its repository is SQLModel-backed, in-memory, or a Postgres adapter.

The change-detection step iterates `MUTABLE_FIELDS` (not the patched-fields dict) and compares pre- and post-values returned from the repository's tuple contract. This means the service never needs to do a second fetch — the _only_ reason it knew the pre-state is because `replace()` / `patch()` already returned both. The rationale for the layered fire order (`TaskUpdated` → `TaskStatusChanged` → `TaskCompleted`) is captured in §4.3; the conditions themselves are owned by FRD §5.1.

**`EmptyUpdateError(422)`** is raised at the top of `patch()` when `fields` is empty. The `read_only_field` check lives in the global handler (§8.1) because it's a framework-level rejection — Pydantic's `extra="forbid"` raises it before the route handler is even invoked.

### 6.2 Data Transfer Objects

> **Implements:** FRD §3.2 (request/response schemas), §3.3 (list query params).

Five Pydantic V2 models in `application/dto.py`:

| DTO                | Role                        | Notable config                                                                                              |
| ------------------ | --------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `TaskCreate`       | `POST` and `PUT` body       | `extra="forbid"` rejects `id`/`created_at` and unknown fields; `title: NonBlankTitle`                       |
| `TaskPatch`        | `PATCH` body                | All fields optional; `title: NonBlankTitle \| None`; `extra="forbid"`                                       |
| `TaskResponse`     | All single-task responses   | `from_attributes=True` so the route can return the raw `Task`; `created_at` serialised as RFC 3339 with `Z` |
| `TaskListResponse` | `GET /v1/tasks` response    | Wraps `items`, `total`, `limit`, `offset`                                                                   |
| `TaskListParams`   | Bound query-param container | Built by the `get_task_query_params` dependency; service layer takes a single typed object, not 5 kwargs    |

`PUT` deliberately reuses `TaskCreate` (no separate `TaskReplace` class) because PUT requires every field — there's nothing to add.

**`NonBlankTitle`** is a reusable Pydantic V2 `Annotated` alias that combines the length bounds with an `AfterValidator(_require_non_blank_title)`. Both `TaskCreate` and `TaskPatch` use it by reference, so the whitespace-only-title rejection rule is defined once. This is the idiomatic V2 replacement for hand-rolled `@field_validator` decorators duplicated across DTOs.

`created_at` serialisation deserves a note: SQLite strips tzinfo on roundtrip, so the value read back is naive-but-UTC-by-convention. `TaskResponse._serialize_created_at` calls `ensure_utc()` from `app/core/datetime_utils.py` to restore tzinfo and emits the value as RFC 3339 with an explicit `Z` UTC marker (FRD §2.4).

---

## 7. Infrastructure

**Purpose.** Implement the ports the application defines, talk to the framework (FastAPI) and the data store (SQLModel/SQLite). Anything that touches a third-party library lives here.

### 7.1 `SQLModelTaskRepository` — the storage adapter

> **Pure design — no FRD clause.** Adapter mechanics; the storage port (§5) is internal.

Implements `TaskRepositoryInterface` against SQLModel sessions. The adapter is responsible for three concerns the application layer must not see:

1. **Translating driver errors into domain errors.** `IntegrityError` whose payload contains `"title_key"` becomes `DuplicateTaskError(details={"title": title})`. Any other `IntegrityError` re-raises so unexpected failures aren't silently mapped to a wrong code. The translation is centralised in `_commit_or_translate(title)` — every write path that actually mutates state calls it (no-op PATCH short-circuits).
2. **Honouring the single-fetch tuple contract.** `replace()` and `patch()` capture `previous = task.snapshot()` _before_ mutating in place, then return `(previous, task)` after `_commit_or_translate(...)` (skipped when no mutable field actually changed). The service layer pays exactly one `get()` per write.
3. **Pagination + sort + filter for `list()`.** The query is built dynamically: optional `WHERE status IN (...)` for filters; primary `ORDER BY <order_by>` using `getattr(Task, order_by)` (`order_by` is a `TaskSortField` StrEnum whose value is the column name); secondary `ORDER BY created_at ASC` as a deterministic tiebreaker; `LIMIT/OFFSET` for pagination. A separate `SELECT COUNT(*)` returns `total`.

> **Decision.** SQLite + `StaticPool`, Phase 1 only. SQLAlchemy's default pool gives each new connection its own private `:memory:` database — schema created in one connection is invisible to the next. `poolclass=StaticPool` + `connect_args={"check_same_thread": False}` forces every session to share one connection. The cost: writes serialise on that connection (which is why `hurl-e2e` runs with `--jobs 1`). The benefit: the test suite, the app, and the readiness probe all see the same schema. This quirk evaporates the day Postgres replaces SQLite.

### 7.2 Event listener (`log_event`)

> **Implements:** FRD §5.2 (built-in logging listener for Phase 1).

A single subscriber lives in `infrastructure/listeners.py`. It receives any `Event`, extracts `event_type`, `event_id`, and `task_id` (when present), and emits one structured log line via the project's `logger`. The listener is registered at startup against all five events by `register_listeners(bus)` — called from the lifespan handler so `app.main` doesn't need to know the concrete event types.

Phase 2 sinks (Slack notifier on `TaskCompleted`, audit log on `TaskUpdated`) follow the same pattern: a function that takes an `Event`, registered once in this module.

### 7.3 FastAPI router (the HTTP adapter)

> **Implements:** FRD §3.1 (endpoint summary), §3.4 (error envelope wiring on every route).

The `api/v1/router.py` module is the only place inside the feature that imports `fastapi`. Each of the six endpoints does three things and three things only:

1. Accepts a typed DTO body and query-params via `Annotated[X, Depends(...)]` injections (no `Depends()` defaults — fully Annotated style).
2. Calls one method on `TaskService`, awaits it, passes `BackgroundTasks` through for event publishing.
3. Returns either the raw `Task` (which `response_model=TaskResponse` converts via `from_attributes=True`) or `None` for the 204 path.

The route handlers carry no business logic — every "if duplicate then…" / "if not found then…" branch lives in the service or the repository, surfaces via a typed exception, and is converted to the envelope by the global handler.

**OpenAPI response examples** for 404/409/422 are wired via `responses={…}` on every decorator, pulling from `app/core/openapi_responses.py` so `/docs` shows the realistic envelope shape (not just the bare HTTP status) on every failure mode. The blocks there read directly from the `ErrorCode` StrEnum so they cannot drift from the live values.

---

## 8. Cross-Cutting Infrastructure (`app/core/`)

**Purpose.** House anything that isn't owned by a single feature: error envelope, event bus, logging, middleware, health probes, configuration, database session factory, dependency providers.

### 8.1 `AppError`, `ErrorCode`, and the global handler

> **Implements:** FRD §3.4 (envelope shape), §4 (error codes and HTTP mapping).

All three concerns — the stable code enum, the exception hierarchy, and the FastAPI handler that converts both `AppError` _and_ Pydantic `RequestValidationError` to the envelope — live in **one file** (`core/errors.py`) because they always change together.

- **`ErrorCode` (StrEnum):** the contract surface. Any consumer can switch on `error.code`.
- **`AppError` hierarchy:** `AppError` (500/`internal_error`) → `ValidationError` (422), `ConflictError` (409), `NotFoundError` (404). Feature errors (§4.4) inherit from these and pin their own code + default message.
- **`register_exception_handlers(app)`:** wires two handlers — one for any `AppError`, one for `RequestValidationError`. Both produce the FRD §3.4 envelope. The validation handler also detects `extra_forbidden` errors on server-owned fields (`id`, `created_at`) and translates them to `ErrorCode.READ_ONLY_FIELD` so callers see the same code regardless of which DTO rejected the body.

The `ctx` field is stripped from Pydantic error rows because it carries the non-JSON-serialisable source exception; `msg` carries the text. The handler reads `request.state.request_id` populated by `RequestIDMiddleware` (§8.4) so every envelope is log-correlatable.

### 8.2 Event Bus (`core/event_bus.py`)

> **Pure design — no FRD clause.** FRD §5 specifies which events fire; this section captures bus mechanics.

**Pattern.** In-memory publish/subscribe.

**API surface.** Three operations: `subscribe(event_type, handler)`, `publish(event, background_tasks)`, and the `Event` base class (`id: UUID`, `occurred_at: datetime`). Subscriptions are stored in a `defaultdict(list)` keyed by event class; `publish()` iterates the handlers for `type(event)` and appends each one to `background_tasks` — so handlers run _after_ the HTTP response is sent.

**Background Tasks integration.** FastAPI's `BackgroundTasks` is the seam: the request handler returns immediately, the response is flushed to the client, then the background tasks run on the same event loop. The bus does not call handlers inline — that would block the response on a slow listener.

> **Decision.** Phase 1 deliberately omits retry, dead-letter queues, circuit breakers, and deduplication. They have not earned their weight at this scale; revisit if the event bus ever crosses a process boundary (e.g., when the Slack notifier in PRD §12 lands and starts hitting flaky external APIs).

### 8.3 Structured logging (`core/logging.py`)

> **Implements:** FRD §7 (structured logging, JSON in qa/prod, request-id correlation).

`structlog` is the standard structured-logging library for Python production services. The `setup_logging()` function configures a processor chain: `merge_contextvars` (pulls request-scoped data), `add_log_level`, ISO timestamps in UTC, stack-info renderer, exception-info formatter, and finally either `JSONRenderer` (qa/prod) or `ConsoleRenderer` (dev/test). The filter level comes from `settings.log_level_int`, which keys off `APP_ENV`.

The exported `logger` is a `structlog` bound logger; any handler that calls `logger.info("event_name", key=value, …)` produces a single-line structured record. Request-ID propagation is automatic because the middleware (§8.4) binds it into `contextvars` before each request.

### 8.4 Request-ID middleware (`core/middleware.py`)

> **Implements:** FRD §7 (X-Request-ID header round-trip, log-context binding).

A Starlette `BaseHTTPMiddleware` subclass with one responsibility: ensure every request has an `X-Request-ID` and that every log line carries it.

**On request:**

1. Read `X-Request-ID` from the inbound headers or generate `str(uuid4())` if absent.
2. Attach it to `request.state.request_id` so the global exception handler and any route can read it.
3. Bind it into `structlog.contextvars` so the `merge_contextvars` processor (§8.3) injects it into every log line emitted during the request.

**On response:** echo the same id back as `X-Request-ID`, then `clear_contextvars()` so the binding doesn't leak across requests (this happens in a `finally` block — even exceptions don't leave a stale binding).

### 8.5 Health endpoints (`core/health.py`)

> **Implements:** FRD §3.1 (`/healthz`, `/readyz` rows), §7 (operational endpoint semantics).

Two endpoints with different intents:

- **`GET /healthz` — liveness.** Returns `{"status": "ok"}` synchronously. No I/O. Used by the orchestrator (Docker healthcheck, k8s liveness probe) to detect a wedged process.
- **`GET /readyz` — readiness.** Runs `SELECT 1` against the injected session; returns `{"status": "ready"}` on success or `503 {"status": "not_ready", "error": …}` on `OperationalError`/`DatabaseError`. Used to gate traffic routing — failures here mean "don't send me requests yet."

Both are `async def` to match the route convention (CLAUDE.md). They live under their own router with `tags=["operational"]`, which feeds the custom OpenAPI operation-id function so they don't collide with feature routes.

### 8.6 Configuration (`core/config.py`)

> **Implements:** FRD §6 (per-env files, variable reference, APP_ENV → defaults matrix).

`pydantic-settings` with two layers of resolution:

1. **Per-environment `.env.<APP_ENV>` file** — `_resolve_env_file()` looks at `os.getenv("APP_ENV", "dev")` at import time and returns the path to `.env.dev` / `.env.test` / `.env.qa` / `.env.prod` if it exists. `.env.example` is the only file checked in; the real per-env files are gitignored and `.dockerignore`-ignored.
2. **Process env vars override file contents** — so k8s ConfigMaps, CI secrets, and `APP_ENV=qa LOG_LEVEL=DEBUG uv run …` all win without editing files.

The `Settings` class exposes three derived properties driven by the `APP_ENV → defaults` matrix (FRD §6.3): `log_level_int`, `json_logs`, `expose_stack_traces`. The matrix is implementation, not contract — change it here and everything that reads `settings.json_logs` (logging, middleware, error handler) follows.

### 8.7 Lifespan and the app factory (`app/main.py`)

> **Pure design — no FRD clause.**

**Pattern.** Factory Method + Lifespan-managed resources.

The `create_app()` function is the single entrypoint: it builds the `FastAPI` instance, attaches the `RequestIDMiddleware`, registers exception handlers, mounts the health router and the tasks router (prefixed by `settings.api_prefix`), and configures the custom OpenAPI operation-id function (`<tag>-<route_name>`, which keeps generated client SDKs readable).

The `lifespan` async context manager owns startup and shutdown:

1. `setup_logging()` — configure `structlog` once.
2. `init_schema()` — create tables on the shared StaticPool connection (Phase 1; Phase 2 swaps this for migrations).
3. `EventBus()` instance + `register_task_listeners(bus)` — wire the five `Task*` events to the logging listener. The feature owns its event-type tuple; `app.main` stays decoupled.
4. `app.state.event_bus = bus` — exposed so `get_event_bus` (§8.8) can hand it to route handlers.
5. On shutdown: emit a structured log line. No connection teardown needed for in-memory SQLite.

### 8.8 Dependency Injection

> **Pure design — no FRD clause.**

**Pattern.** FastAPI's `Depends()` dependency-injection container, used in **Annotated style** (FastAPI 0.95+).

Two layers of providers:

- **Core providers (`core/dependencies.py`):** `get_session()` (yields a SQLModel `Session` from the shared `session_factory`), `get_event_bus(request)` (reads `request.app.state.event_bus` set by the lifespan).
- **Feature providers (`services/tasks/dependencies.py`):** compose the core providers into feature-level dependencies. `get_repository(session)` returns a `SQLModelTaskRepository`; `get_task_service(repo, events)` returns a fully wired `TaskService`. Each is paired with a typed alias — `SessionDep`, `EventBusDep`, `RepositoryDep`, `TaskServiceDep`, `TaskQueryParamsDep` — so route signatures read like `service: TaskServiceDep` rather than `service: TaskService = Depends(get_task_service)`.

The Annotated style means:

1. Dependencies are declared at the **type** level — `Annotated[TaskService, Depends(get_task_service)]` — not as default arguments. mypy can reason about them; refactor tools follow them.
2. Aliases compose. `RepositoryDep` is `Annotated[TaskRepositoryInterface, Depends(get_repository)]`; the route declares `service: TaskServiceDep` and never sees the chain underneath.
3. Swapping a collaborator (e.g. an `AsyncTaskRepository` in Phase 2) means editing one alias and one provider — call sites are unchanged.

---

## 9. Testing Strategy

> **Implements:** FRD §9 (test categories, split rule, coverage gate).

The project uses a **hybrid layout**: unit tests live with the feature module, every other category lives under the project-root `tests/` directory. Category-by-category definitions and scope live in FRD §9.1; this section captures the _how_ — pytest config, Hurl filename conventions, Schemathesis ASGI loader.

### 9.1 `pyproject.toml` — pytest config

> **Pure design.**

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

> **Pure design.** Hurl filename convention and example scenario; FRD §9.1 names Hurl as the E2E tool.

Hurl files use plain descriptive filenames — one scenario per file.

```
tests/hurl/
├── aaa_sort_priority.hurl                    # default + explicit + reverse sort, created_at tiebreak (aaa_ prefix forces first run)
├── healthz.hurl                              # GET /healthz
├── readyz.hurl                               # GET /readyz
├── request_id_propagation.hurl               # X-Request-ID round-trip
├── task_create.hurl                          # POST 201 + capture id
├── task_create_duplicate_title.hurl          # 409 duplicate_task envelope
├── task_create_validation_errors.hurl       # 422 across fields
├── task_full_flow.hurl                       # extended end-to-end scenario beyond task_lifecycle
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

> **Pure design.**

```python
# tests/e2e/test_schemathesis.py
import pytest
import schemathesis

from app.main import app

schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@pytest.mark.e2e
@schema.parametrize()
def test_no_5xx_and_schema_conformance(case: schemathesis.Case) -> None:
    case.call_and_validate()
```

Complements the Hurl scenario tests by generating property-based cases the human writer never thought of. Phase 1 ships it as opt-in (gated by the `e2e` pytest marker; the default `addopts` filter `-m 'not e2e'` keeps `make test` fast). Run explicitly via `make schemathesis`, which calls `pytest -m e2e`. The ASGI loader (`schemathesis.openapi.from_asgi`) runs the property tests in-process against the live FastAPI app — no running container required. Phase 2 wires it into the default CI pipeline.

### 9.4 Coverage gate

> **Implements:** FRD §9.3 (≥ 80% coverage gate).

`pytest --cov=app --cov-fail-under=80` runs against unit + integration + contract layers. Hurl and Schemathesis do not contribute to the Python coverage number — they assert behavior, not code coverage.

---

## 10. Tooling

> **Implements:** FRD §10 (mandated tool list and gates). This section captures concrete configs; FRD names the tools and what they gate.

### 10.1 `pyproject.toml` (highlights)

> **Pure design.**

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

> **Phase 2 tooling considerations** (single source of truth — referenced from FRD §12):
>
> - `import-linter` is **not** in dev deps. Boundaries are enforced by code review. Reintroducing it is a Phase 2 option if the team grows beyond one squad.
> - **Schemathesis** is opt-in via the `e2e` pytest marker (§9.3). Phase 2 promotes it to a required CI gate once the OpenAPI surface stabilises.

### 10.2 `Dockerfile`

> **Pure design.**

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

> **Pure design.**

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

> **Pure design.**

Required targets — additional developer-convenience targets (`all`, `test-contract`, `run`, `docker-build`, `compose-*`, `clean`, `clean-all`, `port-check-kill`, `help`) extend this set; `make help` is self-documenting.

```makefile
.PHONY: install lint typecheck test test-unit test-integration test-contract hurl-e2e schemathesis

install:
	uv sync --all-groups
	uv run pre-commit install

lint:
	uv run ruff check app tests
	uv run ruff format --check app tests
	uv run bandit -c pyproject.toml -r app -q

typecheck:
	uv run mypy

# Test discovery is path-based. The full suite runs with the default coverage
# gate (--cov-fail-under=80); individual layers run with --no-cov for speed.
test:
	uv run pytest

test-unit:
	uv run pytest app/services --no-cov

test-integration:
	uv run pytest tests/integration --no-cov

test-contract:
	uv run pytest tests/contract --no-cov

# ``--jobs 1`` is mandatory: in-memory SQLite + StaticPool serialises on a
# single shared connection, so Hurl's default parallel runs race on session
# state. Trap on EXIT guarantees compose teardown even if up --wait fails.
hurl-e2e:
	@trap 'docker compose -f docker/docker-compose.yaml down' EXIT; \
	docker compose -f docker/docker-compose.yaml up -d --wait task-service && \
	hurl --test --jobs 1 \
	     --variable base_url=http://localhost:8000 \
	     --report-html reports/hurl/ \
	     --report-json reports/hurl/report.json \
	     tests/hurl/*.hurl

# Opt-in property tests. ASGI in-process via schemathesis 4.x — no container
# required. Default ``pytest`` excludes them via ``-m 'not e2e'`` in addopts.
schemathesis:
	uv run pytest -m e2e --no-cov
```

### 10.5 CI (representative pipeline)

> **Pure design.**

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

> **Implements:** FRD §2.4 (UTC everywhere), §8 (concurrency model — single uvicorn worker).

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

> **Implements:** FRD §8 (non-functional baseline — bandit gate, input validation, no stack traces in qa/prod).

The service is internal and unauthenticated in Phase 1. To avoid accidentally publishing it to the internet:

- The Dockerfile binds to `0.0.0.0:8000` but **does not** publish the port by default in `docker-compose.yaml`; the operator must opt in.
- CORS is **off** by default (no `CORSMiddleware`). Phase 2 will introduce a configured allow-list when the SPA lands.
- All inputs are validated by Pydantic; no string concatenation reaches SQL — SQLModel parameterizes everything.
- Error responses **never** include stack traces in `qa` or `prod` (per FRD §6); only `dev` exposes them.
- `bandit` runs in CI to catch common Python security pitfalls.

---

## 13. Best Practices Summary

> **Pure design — recap of decisions captured above.** Item 1 → §1 / §3; item 2 → §4.1 / §6.2; item 3 → §5; items 4–6 → §4.4 / §8.1 / §4.3 / §8.2; items 7–9 → §5 / §9; items 10–11 → §8.6 / §8.3 / §8.4.

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
