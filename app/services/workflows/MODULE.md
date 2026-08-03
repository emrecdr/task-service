# Module: Workflows

> **Canonical specs** live in `docs/`. This file is a code-adjacent index that
> summarises what the feature delivers and points at the authoritative docs.
>
> - Functional contract (endpoints, errors): [`docs/FRD.md`](../../../docs/FRD.md) §2.2–2.3, §3.1, §4
> - Technical implementation spec: [`docs/TIS.md`](../../../docs/TIS.md) §4.2, §8.8

## Responsibility

The **workflow definition as runtime data**: which task states exist, which
are entry points, and which named transitions between them are legal. The
definition is user-owned — reshaping the state machine is a `PUT`, not a
deploy. The tasks feature consults the active definition to enforce every
status change (see `tasks/MODULE.md`); this feature owns storing, validating,
and versioning the definitions themselves.

Ported from the `arjan/src/workflow` reference design: immutable value
objects with an open `meta` extension model, an encapsulated definition
class, and a collect-all-errors document boundary. `WorkflowEngine`
(`domain/engine.py`) applies an active definition's rules — entry
resolution, move legality, completion — so any status-governed feature
(tasks today) drives one engine instead of re-deriving the taxonomy;
`TaskService` remains the transactional executor and the `EventBus` the
observer seam.

## Model

### Definition document (wire + storage form)

```json
{
  "states": [{ "name": "new", "initial": true }, "in_progress",
             { "name": "completed", "completes": true }],
  "transitions": [{ "name": "Start work", "from": "new", "to": "in_progress",
                    "color": "#1f6feb" }]
}
```

- A bare string state is shorthand for a state with no properties.
- `initial` marks a legal entry point for new tasks; the first state (or the
  first `initial` one) is the `default_entry`.
- Every key that is not a core field is **meta** — it travels with the
  definition, round-trips untouched, and the workflow machinery never
  interprets it. The engine reads exactly one meta key: `"completes": true`
  (`COMPLETES_META_KEY`) marks completion, which the tasks feature reacts to
  by firing `TaskCompleted`.
- Unknown **top-level** keys are rejected — that is also what rejects the
  server-owned `version`/`created_at` in `PUT` bodies.

### Validation (serialization.py)

`workflow_from_document` collects **all** problems in one pass (shape errors,
blank names, duplicate states/pairs, unknown state references, unreachable
states) and raises a single `WorkflowValidationError` listing every one.
Value-object constructors are the validators — rules cannot drift between
layers.

## Storage

`workflow_definitions` table, **append-only**: each `PUT` inserts an
immutable row (`version = max+1`, JSONB `document`, `created_at`); the active
definition is the highest version. Rollback = re-`PUT` an older document.
`infrastructure/seed.py` writes the behavior-identical default (any → any
over `new`/`in_progress`/`completed`) when the table is empty — called from
both the app lifespan and the test schema reset, idempotently.

## Endpoints

All under `settings.api_prefix` (default `/v1`):

| method | path        | response | notes                                            |
| ------ | ----------- | -------- | ------------------------------------------------ |
| GET    | `/workflow` | 200      | `{version, created_at, definition}` — canonical re-serialization |
| PUT    | `/workflow` | 200/409/422 | validate → strand guard → append version; fires `WorkflowUpdated` |

The **strand guard**: a definition that would leave existing tasks in states
it no longer defines is rejected with 409 `workflow_states_in_use`, listing
each offending state with its live task count. The usage-count → check →
commit span is guarded by a Postgres transaction-scoped **reader/writer**
advisory lock (`acquire_workflow_guard(shared=...)`, released at the span's
single commit): a workflow replace takes the EXCLUSIVE `pg_advisory_xact_lock`,
which waits for and blocks all in-flight task writes, so no status change can
interleave the usage-count → check → commit. Task-status writes take the SHARED
`pg_advisory_xact_lock_shared` — they only *read* the definition, so they run
concurrently across workers instead of serialising against each other.

## Errors (FRD §4)

| exception                  | status | `error.code`                  |
| -------------------------- | ------ | ----------------------------- |
| `WorkflowValidationError`  | 422    | `invalid_workflow_definition` |
| `WorkflowStatesInUseError` | 409    | `workflow_states_in_use`      |

`WorkflowEngine` raises `InvalidTransitionError` (409 `invalid_transition`)
and `UnknownStatusError` (422 `unknown_status`); both live in
`app/core/errors.py` — a domain engine may not import a feature `errors.py`,
so they sit in core alongside the other cross-cutting enforcement error,
`ReadOnlyFieldError`.

## Layering

```
api/            ← GET/PUT /v1/workflow router
application/    ← WorkflowService (validate → strand guard → store) + WorkflowResponse
domain/         ← State/Transition value objects, Workflow definition, WorkflowEngine, WorkflowUpdated
infrastructure/ ← WorkflowRecord (JSONB column) + repository, seed, log listener
interfaces.py   ← WorkflowRepositoryInterface + StatusUsagePort ABCs + StoredWorkflow
serialization.py← document boundary (feature root: shared by HTTP, storage, seed)
errors.py       ← feature-typed exceptions, inheriting from app.core.errors
dependencies.py ← DI wiring; adapts the tasks repository to StatusUsagePort for the strand guard
```

Cross-feature seam: `WorkflowService` receives the narrow `StatusUsagePort`
(only `count_by_status`, adapted from the tasks repository in
`dependencies.py`) and `TaskService` drives a `WorkflowEngine` built from the
active definition — acyclic at the interfaces layer, both repositories built
from the same request session.
