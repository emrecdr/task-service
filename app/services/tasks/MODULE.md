# Module: Tasks

> **Canonical specs** live in `docs/`. This file is a code-adjacent index that
> summarises what the feature delivers and points at the authoritative docs.
>
> - Product scope: [`docs/PRD.md`](../../../docs/PRD.md)
> - Functional contract (endpoints, errors, events): [`docs/FRD.md`](../../../docs/FRD.md)
> - Technical implementation spec: [`docs/TIS.md`](../../../docs/TIS.md)

## Responsibility

CRUD for internal *tasks* — short titled work items with a status, a priority,
and a structured event trail so downstream consumers can react to lifecycle
changes without polling. Uniqueness is enforced on a normalised title key,
not the display title, so `"Ship plan"` and `"  ship plan  "` collide.

## Models

### Task (`app/services/tasks/domain/models.py`)

**Table:** `tasks` — Phase 1 stores via the SQLModel row directly; there is no
separate ORM/domain split (TIS §4.1 Decision callout).

**Key fields:**

| field         | type            | notes                                                            |
| ------------- | --------------- | ---------------------------------------------------------------- |
| `id`          | `int` PK        | server-owned; PUT/PATCH bodies containing `id` are rejected      |
| `title`       | `str` 1..200    | preserved verbatim for display                                   |
| `title_key`   | `str` UNIQUE    | canonical uniqueness key = `title.strip().casefold()` (FRD §2.4) |
| `description` | `str` 0..2000   | optional                                                         |
| `status`      | `Status` enum   | `new`, `in_progress`, `completed`                                |
| `priority`    | `int` 1..5      |                                                                  |
| `created_at`  | `datetime UTC`  | server-owned; aware datetime; RFC 3339 with `Z` suffix on wire   |

**Domain invariants:**

- `title_key` is the only column the duplicate-detection path reads — it's
  derived from `Task.clean_title(title)` and never set by callers directly.
- All timestamps are `datetime.now(UTC)`; naive datetimes are a bug (FRD §2.4).
- `id` and `created_at` are server-managed. Inbound DTOs (`TaskCreate`,
  `TaskPatch`) use `extra="forbid"` so attempts to set them surface as
  `read_only_field` (422).

## Enums

`app/services/tasks/enums.py::Status` — `new`, `in_progress`, `completed`. The
only valid lifecycle transitions are open; the service enforces no state
machine in Phase 1 (any → any is allowed).

## Events (FRD §5.1)

All five are defined in `domain/events.py` and fire post-commit via
`EventBus.publish(event, background_tasks)` so listeners never block the
HTTP response:

| event                | fires when                                                  |
| -------------------- | ----------------------------------------------------------- |
| `TaskCreated`        | after a successful `POST /v1/tasks`                          |
| `TaskUpdated`        | only when at least one mutable field actually changed        |
| `TaskStatusChanged`  | only when `status` was among the changed fields              |
| `TaskCompleted`      | convenience fanout — when `status` transitioned to `completed` |
| `TaskDeleted`        | after a successful `DELETE`, carrying the pre-delete snapshot |

Mutable fields (`{"title", "description", "status", "priority"}`) are the
single source of truth in `domain/models.py::MUTABLE_FIELDS` — the service
imports it for change-detection and `Task.patch()` imports it for patch-dict
validation. The repository stays out of mutability enforcement (domain
concern).

## Errors (FRD §4)

All raised exceptions inherit from `app.core.errors.AppError` and convert to
the standard envelope (`{"error": {"code","message","details","request_id"}}`)
via the global handler. Never raise plain `Exception` — that bypasses the
envelope and surfaces as 500.

| exception              | status | `error.code`        |
| ---------------------- | ------ | ------------------- |
| `DuplicateTaskError`   | 409    | `duplicate_task`    |
| `TaskNotFoundError`    | 404    | `task_not_found`    |
| `EmptyUpdateError`     | 422    | `empty_update`      |
| `ReadOnlyFieldError`   | 422    | `read_only_field`   |

## Endpoints

All under `settings.api_v1_prefix` (default `/v1`):

| method | path             | response | events fired                         |
| ------ | ---------------- | -------- | ------------------------------------ |
| POST   | `/tasks`         | 201      | `TaskCreated`                        |
| GET    | `/tasks`         | 200      | —                                    |
| GET    | `/tasks/{id}`    | 200/404  | —                                    |
| PUT    | `/tasks/{id}`    | 200/404/409 | `TaskUpdated`(+`StatusChanged`+`Completed`)* |
| PATCH  | `/tasks/{id}`    | 200/404/409/422 | same as PUT*                     |
| DELETE | `/tasks/{id}`    | 204/404  | `TaskDeleted`                        |

\* events only fire when the corresponding fields actually changed.

## Layering

Feature is hexagonal-internal (see `CLAUDE.md` for the full rule):

```
api/        ← FastAPI routes; only place that imports fastapi inside the feature
application/← TaskService + DTOs; depends on domain/ and interfaces.py
domain/     ← Task entity + events + MUTABLE_FIELDS; pure data + invariants
infrastructure/ ← SQLModelTaskRepository + log_event listener
interfaces.py   ← TaskRepositoryInterface ABC (Status / TaskSortField enums in constants.py)
errors.py       ← feature-typed exceptions, all inheriting from app.core.errors
dependencies.py ← FastAPI providers composing repo → service
```
