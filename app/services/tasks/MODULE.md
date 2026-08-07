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

| field         | type                    | notes                                                            |
| ------------- | ----------------------- | ---------------------------------------------------------------- |
| `id`          | `uuid.UUID` PK (UUIDv7) | server-owned; PUT/PATCH bodies containing `id` are rejected      |
| `title`       | `str` 1..200            | preserved verbatim for display                                   |
| `title_key`   | `str` UNIQUE            | canonical uniqueness key = `title.strip().casefold()` (FRD §2.5) |
| `description` | `str` 0..2000           | optional                                                         |
| `status`      | `str`                   | a state of the **active workflow definition** (seed: `new`, `in_progress`, `completed`) |
| `priority`    | `int` 1..5              |                                                                  |
| `created_at`  | `datetime UTC`          | server-owned; aware datetime; RFC 3339 with `Z` suffix on wire   |

**Domain invariants:**

- `title_key` is the only column the duplicate-detection path reads — it's
  derived from `Task.clean_title(title)` and never set by callers directly.
- All timestamps are `datetime.now(UTC)`; naive datetimes are a bug (FRD §2.4).
- `id` and `created_at` are server-managed. Inbound DTOs (`TaskCreate`,
  `TaskPatch`) use `extra="forbid"` so attempts to set them surface as
  `read_only_field` (422).

## States

Task states are **runtime data** owned by the active workflow definition
(`app/services/workflows/`, `GET/PUT /v1/workflow`) — there is deliberately no
status enum. The service drives a `WorkflowEngine` (built from the active
definition) that enforces the transition table on every status change; the
shipped seed is behavior-identical to the original any → any contract. The
state-meta flag that fires `TaskCompleted` is `COMPLETES_META_KEY`, which the
engine reports via `completes()` and this feature reacts to; it is defined
with the document vocabulary in `workflows/domain/models.py`.

## Events (FRD §5.1)

All five are defined in `domain/events.py`. The service builds them and hands
them to the repository, which stages them into the `outbox` table **in the same
transaction** as the row change; the in-process outbox relay then delivers them
to listeners off the request path (at-least-once), so they never block the HTTP
response:

| event                | fires when                                                  |
| -------------------- | ----------------------------------------------------------- |
| `TaskCreated`        | after a successful `POST /v1/tasks`                          |
| `TaskUpdated`        | only when at least one mutable field actually changed        |
| `TaskStatusChanged`  | only when `status` was among the changed fields              |
| `TaskCompleted`      | convenience fanout — when the entered state carries `"completes": true` |
| `TaskDeleted`        | after a successful `DELETE`, carrying the pre-delete snapshot |

Mutable fields (`{"title", "description", "status", "priority"}`) are the
single source of truth in `domain/models.py::MUTABLE_FIELDS`. `Task.changed_fields()`
derives the changed set from it — the service gates both the write and event fan-out
on it (a no-op change skips `persist` entirely, committing nothing and staging no
events) — while `Task.apply_patch()` uses it for patch-dict validation. The repository
stays out of mutability enforcement (domain concern).

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

`read_only_field` (422) is emitted by the core handler when the request body
sets a server-managed field (`id`, `created_at`); the exception class
(`ReadOnlyFieldError`) lives in `app.core.errors`, not this feature.

`invalid_transition` (409), `unknown_status` (422), `transition_forbidden`
(403) and `wip_limit_exceeded` (409) surface on the write endpoints but are
raised by `WorkflowEngine`; their classes (`InvalidTransitionError`,
`UnknownStatusError`, `TransitionForbiddenError`, `WipLimitExceededError`)
also live in `app.core.errors`, not this feature. The last two are the
`meta`-declared workflow guards: a transition's `roles` guard refuses an actor
who holds none of them (roles arrive via the provisional `X-Roles` header), and
a state's `wip_limit` refuses entry once it is full.

## Endpoints

All under `settings.api_prefix` (default `/v1`):

| method | path             | response | events fired                         |
| ------ | ---------------- | -------- | ------------------------------------ |
| POST   | `/tasks`         | 201/409/422 | `TaskCreated`                     |
| GET    | `/tasks`         | 200/422  | —                                    |
| GET    | `/tasks/{id}`    | 200/404/422 | —                                 |
| PUT    | `/tasks/{id}`    | 200/403/404/409/422 | `TaskUpdated`(+`StatusChanged`+`Completed`)* |
| PATCH  | `/tasks/{id}`    | 200/403/404/409/422 | same as PUT*                 |
| DELETE | `/tasks/{id}`    | 204/404/422 | `TaskDeleted`                     |
| GET    | `/tasks/{id}/transitions` | 200/404/422 | — (legal moves + definition `meta` for UI buttons) |

\* events only fire when the corresponding fields actually changed.

## Layering

Feature is hexagonal-internal (see `CLAUDE.md` for the full rule):

```
api/        ← FastAPI routes; only place that imports fastapi inside the feature
application/← TaskService + DTOs; depends on domain/, interfaces.py, and the workflows WorkflowEngine + interfaces (enforcement seam)
domain/     ← Task entity + events + MUTABLE_FIELDS; pure data + invariants
infrastructure/ ← SQLModelTaskRepository + log_event listener
interfaces.py   ← TaskRepositoryInterface ABC (TaskSortField enum in constants.py)
errors.py       ← feature-typed exceptions, all inheriting from app.core.errors
dependencies.py ← FastAPI providers composing repo → service
```
