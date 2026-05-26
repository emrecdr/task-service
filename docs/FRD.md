# 🛠️ Functional Requirements Document (FRD)

**Project:** Internal Task Service
**Document Version:** 1.0
**Companion to:** `docs/PRD.md`

---

## 1. Architectural Standards

The service follows **simplified Hexagonal Architecture (feature-first)** — each feature module owns its full stack (`api/`, `application/`, `domain/`, `infrastructure/`), with an explicit `interfaces.py` ABC at the feature root for swappable storage. Substitutability and framework isolation are preserved; the ceremony of strict Cosmic-Python hex (a separate `ports/` subfolder, `Protocol` typing, a domain entity class apart from the SQLModel row, CI-enforced import boundaries) is dropped because it is not earned at Phase 1 scale.

| Layer                                      | Responsibility                                                                                                       | Allowed dependencies                                                                     |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| **Domain** (`domain/`)                     | The `Task` SQLModel entity (storage + domain rules in one class), `Status` enum, domain events.                      | stdlib, `pydantic`, `sqlmodel`, shared base classes from `app/core/`. **Not** `fastapi`. |
| **Application** (`application/`)           | `TaskService` use-case orchestration; Pydantic DTOs (`TaskCreate`, `TaskPatch`, `TaskResponse`, `TaskListResponse`). | Domain + `interfaces.py`. **Not** `infrastructure/`, **not** `fastapi`.                  |
| **Repository Interface** (`interfaces.py`) | ABC contracts for storage.                                                                                           | Domain only.                                                                             |
| **Inbound Adapter** (`api/v1/`)            | FastAPI router and request handlers. Mounted by `app/main.py`.                                                       | Application + DI providers.                                                              |
| **Outbound Adapters** (`infrastructure/`)  | `SQLModelTaskRepository`, `log_event` listener, future Postgres/Slack.                                               | Domain + interfaces + session helpers from `app/core/`.                                  |
| **Cross-cutting** (`app/core/`)            | `AppError`, error codes, `EventBus`, `structlog` setup, Request-ID middleware, `/healthz`/`/readyz`, config.         | stdlib + framework. **Not** any individual service.                                      |

**Architectural rules** are enforced by **code review**, not by `import-linter`. Reintroducing a linter for boundary checking is captured in TIS §10.1 as a Phase 2+ option if the team grows beyond one squad.

## 2. Domain Entity

### 2.1 `Task`

| Field         | Type            | Constraint                                                                                                      | Origin                    |
| ------------- | --------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------- |
| `id`          | `int`           | Primary key, auto-incrementing positive integer, server-assigned.                                               | Repository.               |
| `title`       | `str`           | Non-empty after trim; max 200 chars; **unique** across all tasks under a case-insensitive + trimmed comparison. | Caller.                   |
| `description` | `str \| None`   | Optional; max 2000 chars.                                                                                       | Caller.                   |
| `status`      | `Status` (enum) | One of `new`, `in_progress`, `completed`. Default `new` on create.                                              | Caller (default applied). |
| `priority`    | `int`           | Inclusive range 1–5 (`Field(ge=1, le=5)`).                                                                      | Caller.                   |
| `created_at`  | `datetime`      | UTC, timezone-aware, set by repository on insert. Immutable.                                                    | Repository.               |

### 2.2 `Status` enum

```python
class Status(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
```

Wire format is the snake-case string value (`"in_progress"`, not `"in progress"`). The literal in the PDF — "in progress" — is normalized for API stability.

### 2.3 Status transitions

Phase 1 allows **any → any** transition. The service does **not** validate workflow order. Future phases may add this as a configurable policy.

### 2.4 Timezone policy (single source of truth: UTC)

The PDF notes the team is _"spread across multiple time zones."_ To avoid any ambiguity in stand-ups and audit trails, the service treats time as follows:

| Concern       | Rule                                                                                                                                                                                           |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Storage       | All `datetime` columns are **timezone-aware UTC**. The `Task.created_at` field is set by the repository using `datetime.now(UTC)`. Naive `datetime` values are rejected at the model boundary. |
| API responses | Timestamps are serialized as RFC 3339 in UTC with a `Z` suffix — e.g. `"created_at": "2026-05-14T13:01:42Z"`. The service **never** emits offsets like `+02:00`.                               |
| API requests  | Inputs that contain timestamps (none today; reserved for Phase 2 audit/filter use) must be RFC 3339 with explicit `Z` or `+HH:MM`. Naive timestamps are rejected with `422 validation_error`.  |
| Logs          | `structlog`'s `TimeStamper` is configured with `utc=True` so every log line is unambiguously UTC.                                                                                              |
| Container     | The Docker image runs with `TZ=UTC` so any library that falls back to system time still observes UTC.                                                                                          |
| Clients       | Clients are expected to convert to local time at the presentation edge. The service is the single source of truth.                                                                             |

This is a hard rule — any code path that creates or reads a `datetime` without `tzinfo=UTC` is a bug.

### 2.4 Title uniqueness

Comparison key is `title.strip().casefold()`. Examples that **collide**:

- `"Fix bug"`, `"fix bug"`, `" FIX BUG "`, `"fix\tbug"` _(only outer whitespace is trimmed; inner whitespace is significant)_.

Examples that **do not** collide:

- `"Fix bug"` vs `"Fix  bug"` (two spaces).
- `"Fix bug"` vs `"Fix bug!"`.

Duplicate creates and renames that collide must raise `DuplicateTaskError` → HTTP **409 Conflict**.

## 3. API Contract

All routes are mounted under `/v1`. All responses are JSON. All timestamps are RFC 3339 in UTC (`2026-05-14T13:01:42Z`).

### 3.1 Endpoint summary

| Method   | Path             | Purpose                              | Success                       | Error         |
| -------- | ---------------- | ------------------------------------ | ----------------------------- | ------------- |
| `POST`   | `/v1/tasks`      | Create a task.                       | `201 Created` + `Task`        | 409, 422      |
| `GET`    | `/v1/tasks`      | List tasks (filter, sort, paginate). | `200 OK` + `TaskListResponse` | 422           |
| `GET`    | `/v1/tasks/{id}` | Fetch one task.                      | `200 OK` + `Task`             | 404           |
| `PUT`    | `/v1/tasks/{id}` | Replace a task in full.              | `200 OK` + `Task`             | 404, 409, 422 |
| `PATCH`  | `/v1/tasks/{id}` | Update any subset of fields.         | `200 OK` + `Task`             | 404, 409, 422 |
| `DELETE` | `/v1/tasks/{id}` | Delete a task.                       | `204 No Content`              | 404           |
| `GET`    | `/healthz`       | Liveness.                            | `200 OK` `{"status":"ok"}`    | —             |
| `GET`    | `/readyz`        | Readiness (DB session reachable).    | `200 OK` or `503`             | —             |

### 3.2 Request/response schemas

**`TaskCreate`** (POST body):

| Field         | Type   | Required | Notes                   |
| ------------- | ------ | -------- | ----------------------- |
| `title`       | string | yes      | 1–200 chars after trim. |
| `description` | string | no       | ≤ 2000 chars.           |
| `status`      | enum   | no       | Defaults to `new`.      |
| `priority`    | int    | yes      | 1–5.                    |

**`TaskUpdate`** (PUT body): same shape as `TaskCreate` but **every** field is required (full replacement). `created_at` and `id` are server-owned and rejected if present.

**`TaskPatch`** (PATCH body): any subset of `title`, `description`, `status`, `priority`. At least one field must be provided (422 otherwise).

**`TaskResponse`**: all `Task` fields including `id` and `created_at`.

**`TaskListResponse`**:

```json
{
  "items": [
    /* TaskResponse */
  ],
  "total": 137,
  "limit": 100,
  "offset": 0
}
```

### 3.3 List query parameters

| Param    | Type                            | Default         | Notes                                                                                                       |
| -------- | ------------------------------- | --------------- | ----------------------------------------------------------------------------------------------------------- |
| `status`    | `Status` enum  | —          | Filters to that status only. Multiple values supported via `?status=new&status=in_progress`.                       |
| `order_by`  | `priority`     | `priority` | Sort column. Only `priority` is sortable in Phase 1; equal priorities are sub-sorted by `created_at` ascending. |
| `order_dir` | `asc \| desc`  | `desc`     | Sort direction.                                                                                                    |
| `limit`     | int            | `100`      | 1–500. Values outside this range → 422.                                                                            |
| `offset`    | int            | `0`        | ≥ 0.                                                                                                               |

### 3.4 Standardized error body

Every non-2xx response uses the same envelope:

```json
{
  "error": {
    "code": "duplicate_task",
    "message": "A task with this title already exists.",
    "details": { "title": "Fix bug" },
    "request_id": "0c8b…"
  }
}
```

`code` values are stable strings owned by the domain layer; consumers may switch on them.

Malformed JSON request bodies (which FastAPI would otherwise surface as a raw `400 Bad Request`) are rewrapped by the global handler as `422 validation_error` envelopes so callers always see the same shape.

## 4. Error Handling Strategy

| Condition                                                           | Domain exception             | HTTP                        | `code`             |
| ------------------------------------------------------------------- | ---------------------------- | --------------------------- | ------------------ |
| Title already exists (create or rename)                             | `DuplicateTaskError`         | `409 Conflict`              | `duplicate_task`   |
| Task ID not found                                                   | `TaskNotFoundError`          | `404 Not Found`             | `task_not_found`   |
| Empty/over-length title, priority out of range, unknown status      | (Pydantic `ValidationError`) | `422 Unprocessable Entity`  | `validation_error` |
| PATCH body with no fields                                           | `EmptyUpdateError`           | `422 Unprocessable Entity`  | `empty_update`     |
| Attempt to set server-owned field on PUT/PATCH (`id`, `created_at`) | `ReadOnlyFieldError`         | `422 Unprocessable Entity`  | `read_only_field`  |
| Anything else (truly unexpected)                                    | `Exception`                  | `500 Internal Server Error` | `internal_error`   |

A single global FastAPI exception handler converts domain exceptions to the error envelope above. Stack traces are **never** included in production responses (controlled by `APP_ENV`).

## 5. Domain Event System

The service must ship an in-process **Event Bus** (publish/subscribe). Domain events are dispatched **after** the repository write succeeds and **before** the HTTP response is finalized; listeners run via FastAPI `BackgroundTasks` so they never block the response.

### 5.1 Events

| Event               | Fired when                                                                               | Payload                                                                     |
| ------------------- | ---------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `TaskCreated`       | After successful `POST /v1/tasks`.                                                       | `task: TaskResponse`                                                        |
| `TaskUpdated`       | After any successful PUT or PATCH that mutated ≥1 field.                                 | `task: TaskResponse`, `changed_fields: list[str]`, `previous: TaskResponse` |
| `TaskStatusChanged` | When the `status` field is among the changed fields. Fires in addition to `TaskUpdated`. | `task: TaskResponse`, `from_status: Status`, `to_status: Status`            |
| `TaskCompleted`     | When `status` transitions to `completed`. Fires in addition to `TaskStatusChanged`.      | `task: TaskResponse`                                                        |
| `TaskDeleted`       | After successful DELETE.                                                                 | `task: TaskResponse` (the deleted snapshot)                                 |

`TaskCompleted` is a convenience event so listeners do not need to filter `TaskStatusChanged` payloads when they only care about completion.

### 5.2 Built-in listener (Phase 1)

One listener ships in Phase 1: the `log_event` subscriber in `app/services/tasks/infrastructure/listeners.py`. It subscribes to all five events and writes a single structured log line per event, including `request_id`, `event_type`, and the payload's `task.id`.

### 5.3 Adding listeners in the future

Listeners must register at app startup via the dependency-injected `EventBus`. Adding a Slack notifier in Phase 2 is one file: a new adapter that subscribes to `TaskCompleted`.

## 6. Configuration

Configuration is loaded via `pydantic-settings` from environment variables and a **per-environment `.env` file** selected by the `APP_ENV` variable.

### 6.1 Per-environment file layout

| File           | Loaded when    | Purpose                                                                               |
| -------------- | -------------- | ------------------------------------------------------------------------------------- |
| `.env.dev`     | `APP_ENV=dev`  | Local developer machine. Verbose logs, dev DB URL.                                    |
| `.env.test`    | `APP_ENV=test` | Automated test runs (pytest, CI test stage). Quiet logs, isolated DB.                 |
| `.env.qa`      | `APP_ENV=qa`   | Shared QA environment for manual / exploratory testing and pre-production validation. |
| `.env.prod`    | `APP_ENV=prod` | Production.                                                                           |
| `.env.example` | never loaded   | Reference template, checked into VCS. Every other `.env.*` file is gitignored.        |

Rules:

1. The active file is resolved by `APP_ENV` **before** Settings instantiation. If `APP_ENV` is unset, the loader defaults to `dev`.
2. Environment variables already present in the process **override** anything loaded from the file. This means container orchestrators (k8s secrets, Bitbucket Pipelines variables) win over file contents.
3. The Docker image **must not** bake any `.env.*` file in (enforced by `.dockerignore`). The image takes its config from real environment variables; `.env.*` files are a local-development convenience only.
4. Secrets never live in `.env.example`. Use placeholder values such as `__REPLACE_ME__`.

### 6.2 Variable reference

| Variable             | Type                        | Default                       | Purpose                                                           |
| -------------------- | --------------------------- | ----------------------------- | ----------------------------------------------------------------- |
| `APP_ENV`            | `dev \| test \| qa \| prod` | `dev`                         | Selects the `.env.*` file and drives log level + error verbosity. |
| `LOG_LEVEL`          | log-level string            | derived from `APP_ENV`        | Explicit override.                                                |
| `DATABASE_URL`       | str                         | `sqlite+pysqlite:///:memory:` | SQLModel engine URL.                                              |
| `PROJECT_NAME`       | str                         | `Internal Task Service`       | OpenAPI title.                                                    |
| `API_PREFIX`         | str                         | `/v1`                         | Allows hosting under a different base path.                       |
| `DEFAULT_LIST_LIMIT` | int                         | `100`                         | Default pagination limit.                                         |
| `MAX_LIST_LIMIT`     | int                         | `500`                         | Hard cap on pagination limit.                                     |

### 6.3 `APP_ENV` → defaults matrix

| `APP_ENV` | Default `LOG_LEVEL` | JSON logs?            | Stack traces in error responses? |
| --------- | ------------------- | --------------------- | -------------------------------- |
| `dev`     | `DEBUG`             | no (console renderer) | yes                              |
| `test`    | `WARNING`           | no                    | no                               |
| `qa`      | `INFO`              | yes                   | no                               |
| `prod`    | `INFO`              | yes                   | no                               |

## 7. Observability

- **Request-ID middleware:** every incoming request receives an `X-Request-ID` header (generated as a UUIDv4 if absent) and the value is bound to the log context for the duration of the request. Every response carries the same header back.
- **Structured logging:** logs are emitted as single-line JSON when `APP_ENV ∈ {qa, prod}` and as human-readable lines in `dev`. Every line includes `timestamp`, `level`, `request_id`, `event`, and contextual key/value pairs. `test` keeps logs quiet (`WARNING+`) to avoid noisy pytest output.
- **Health endpoints:**
  - `GET /healthz` — returns 200 if the process is up. Synchronous, no I/O.
  - `GET /readyz` — returns 200 only if a trivial repository round-trip succeeds; 503 otherwise.

## 8. Non-Functional Constraints

| Aspect          | Requirement                                                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Python**      | 3.13+                                                                                                                                                             |
| **Framework**   | FastAPI ≥ 0.110                                                                                                                                                   |
| **ORM**         | SQLModel (pinned via `uv.lock`)                                                                                                                                   |
| **Config**      | `pydantic-settings`                                                                                                                                               |
| **Logging**     | `structlog` (with stdlib `logging` interception so library logs route through the same sink). Standard structured-logging library for production Python services. |
| **Async**       | Routes may be `async def`; the repository is synchronous in Phase 1 (SQLite).                                                                                     |
| **Concurrency** | Single uvicorn worker assumed in Phase 1. Adapters must be safe under that model.                                                                                 |

## 9. Test Strategy

The project uses a **hybrid test layout**: unit tests live alongside the feature module (`app/services/<feature>/tests/`); every cross-boundary category lives under the project-root `tests/` directory.

### 9.1 Test categories

| Category           | Where                       | Tooling                                                | What is covered                                                                                                                                                                                                                                                                                                                                                                |
| ------------------ | --------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Unit**           | `app/services/tasks/tests/` | `pytest`                                               | Domain rules on `Task` (title normalization, `title_key` collisions, priority bounds, factory validation). Service-layer orchestration with a fake `TaskRepositoryInterface` and a fake `EventBus`: events fire on correct paths; `TaskCompleted` only fires when status transitions to `completed`; PATCH with no changes does not fire `TaskUpdated`. No FastAPI, no DB I/O. |
| **Integration**    | `tests/integration/`        | `pytest` + `httpx.AsyncClient` against the FastAPI app | All endpoints, all error codes, query-param validation, pagination, error-envelope shape, `X-Request-ID` round-trip. In-process; uses SQLite `:memory:`.                                                                                                                                                                                                                       |
| **Contract**       | `tests/contract/`           | `pytest` parametrized over every concrete repository   | Conformance of any `TaskRepositoryInterface` implementation. Adding a new adapter (e.g., Postgres in Phase 2) requires zero new test code.                                                                                                                                                                                                                                     |
| **E2E (Hurl)**     | `tests/hurl/`               | `hurl` CLI against the running Docker container        | Black-box scenarios over real HTTP. One scenario per file with plain descriptive names (e.g., `task_create.hurl`, `task_lifecycle.hurl`, `healthz.hurl`).                                                                                                                                                                                                                      |
| **E2E (property)** | `tests/e2e/`                | `Schemathesis` driven by the OpenAPI schema            | Property-based testing that asserts no 5xx and schema-conformant responses. Optional in Phase 1, mandatory in Phase 2.                                                                                                                                                                                                                                                         |
| **Static**         | `ruff`, `mypy`, `bandit`    | Lint, type-check, security-lint.                       | Run via `pre-commit` locally and in CI.                                                                                                                                                                                                                                                                                                                                        |

### 9.2 Test split rule

> _Can this test run with only my feature module imported?_ If yes, it's unit and lives in the feature's own `tests/`. If it needs `from app.main import app`, real HTTP, or another feature, it crosses a boundary and lives under `tests/` at the project root.

### 9.3 Coverage gate

Coverage target: **≥ 80%** on the `app/` package (excluding `app/main.py` boot-only code if necessary). `pytest --cov=app --cov-fail-under=80` runs against unit + integration + contract layers. Hurl and Schemathesis assert behavior, not Python coverage.

## 10. Tooling

### 10.1 Runtime + build

| Tool                                       | Purpose                                                                                |
| ------------------------------------------ | -------------------------------------------------------------------------------------- |
| `uv`                                       | Project, dependency, and virtualenv manager. Lockfile: `uv.lock`.                      |
| `pytest` + `pytest-cov` + `pytest-asyncio` | Test runner and coverage.                                                              |
| `httpx`                                    | Async API client for integration tests.                                                |
| `hurl`                                     | E2E scenario runner against the running container. Reports written to `reports/hurl/`. |
| Docker                                     | Single `Dockerfile`; final image runs as a non-root user.                              |

### 10.2 Developer environment (dev-only dependency group)

| Tool                                   | Purpose                                                                                                                                                                                                                                  | Gate                                                   |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `ruff`                                 | Linter + formatter. Run as `ruff check` and `ruff format --check`.                                                                                                                                                                       | `pre-commit` (fast hooks) **and** CI.                  |
| `mypy`                                 | Static type checking (`--strict` on the domain layer, default elsewhere).                                                                                                                                                                | CI.                                                    |
| `bandit`                               | Security linter for common Python pitfalls (`assert` in prod paths, weak crypto, hardcoded passwords). Configured via `[tool.bandit]` in `pyproject.toml`; severity ≥ `medium` fails CI.                                                 | CI.                                                    |
| `pre-commit`                           | Local pre-commit hooks runner. Pinned via `.pre-commit-config.yaml`; runs `ruff`, `ruff format`, `bandit`, end-of-file/whitespace fixers, and `uv lock --check` to keep `uv.lock` in sync. Onboarding step: `uv run pre-commit install`. | Developer machines (locally) **and** CI as a backstop. |
| `schemathesis` _(optional in Phase 1)_ | OpenAPI-driven property-based E2E tests. Promoted to a required gate in Phase 2.                                                                                                                                                         | CI (optional).                                         |

The four mandatory dev-tool gates (`ruff`, `mypy`, `bandit`, `pre-commit`) are wired into both local hooks and CI to ensure no commit reaches `main` without passing them. `import-linter` is **deliberately not used** in Phase 1 — boundaries are enforced by code review. Reintroducing it is a Phase 2 option if the team grows beyond one squad.

## 11. Acceptance Criteria

The Phase 1 release ships when all of the following hold:

1. Every row in Section 3.1 has at least one passing integration test under `tests/integration/services/tasks/`.
2. Every error code in Section 4 has at least one passing integration test asserting the standardized envelope (Section 3.4).
3. Every event in Section 5.1 has at least one passing service-layer **unit test** under `app/services/tasks/tests/` asserting it fires under the right conditions and **does not** fire under the wrong ones.
4. `tests/contract/test_task_repository_interface.py` passes against every concrete `TaskRepositoryInterface` implementation.
5. `tests/hurl/*.hurl` scenarios — at minimum `healthz`, `task_create`, `task_create_duplicate_title`, `task_lifecycle`, `task_list_filter_sort`, `task_not_found` — pass against the running container.
6. `ruff check`, `ruff format --check`, `bandit`, `mypy`, and `pytest --cov=app --cov-fail-under=80` all pass in CI.
7. The Docker image builds and `docker run` of the published tag binds to port 8000 and responds 200 on `/healthz`.
8. README explains run, test, and configuration (including the `APP_ENV` matrix).

## 12. Future Integration Roadmap (Phase 2+)

This section intentionally holds no list. The roadmap split is:

- **Product features** (Postgres, Alembic, RBAC, Slack notifier, `/metrics`, audit log, SPA, …) → **PRD §12**.
- **Tooling considerations** (`import-linter` reintroduction, schemathesis promotion to required gate, …) → **TIS §10.1**.

Adding a Phase 2 item here would create a third source of truth and re-introduce the drift we just cleaned up.
