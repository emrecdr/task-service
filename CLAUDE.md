# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## #1 Rule — Git is OFF LIMITS

- ❌ **NEVER run ANY git command** unless the user EXPLICITLY asks (`git add`, `commit`, `reset`, `checkout`, `push`, `stash`, `revert`, `rebase`, `merge`, `branch` — none of them).
- ❌ No git commands hidden inside scripts or make targets unless requested.
- ❌ No "cleanup" of staging area, branches, or history.
- ✅ Touch git only on a direct instruction ("commit this", "push to remote").
- **Why**: Unauthorized git operations can destroy work irreversibly. Claude assists with code; the user owns version control.

## Collaboration protocol

- **Ask before architectural decisions.** API contract changes, multi-step vs single-step workflows, data-model deviations, new patterns, trade-offs affecting UX or client compatibility → present full context, options with trade-offs, and a recommendation. Don't decide autonomously.
- **State assumptions before implementing.** If a request is ambiguous, name the assumption explicitly in one line and proceed — or ask if the assumption is load-bearing. Don't silently pick one interpretation when multiple are plausible. If multiple reasonable approaches exist, present them with trade-offs instead of choosing in private.
- **Validate before "fixing".** Before changing code to fix a reported problem, confirm the problem actually exists in the current code (search for it, check variable names/signatures/file locations). Many "issues" raised by review agents are theoretical edge cases already prevented by Pydantic/enum/type-safety guarantees.
- **Complexity vs benefit.** If a recommended change adds noticeable code/tests for a theoretical-only gain, stop and surface the trade-off before implementing.
- **Stay in scope — the trace test.** Only implement what was requested or is clearly necessary. Every changed line should trace directly to the user's request; if it doesn't, it's scope creep. Adjacent improvements are proposals, not actions. Don't "improve" adjacent code, comments, or formatting; match the existing style even if you'd write it differently.
- **Orphan cleanup is yours; pre-existing dead code is not.** If your edits leave an import, variable, or function unused, remove it in the same change. If you notice pre-existing dead code unrelated to your edit, mention it — don't delete it unprompted.
- **Goal-driven execution.** Convert vague tasks into verifiable goals *before* coding. "Add validation" → "write failing tests for invalid inputs, then make them pass." "Fix the bug" → "write a reproducer test first, then make it pass." "Refactor X" → "ensure the existing tests pass before and after." For multi-step work, state a brief plan with a verification check per step. Strong success criteria let you loop independently to completion; weak ones ("make it work") force mid-flight clarification.
- **Search existing code before creating new.** Protocols, interfaces, errors, helpers — grep first, reuse what's there, improve in place instead of duplicating.

## Project status

Phase 1 (the internal MVP) is fully implemented and green; **Phase 2 is in progress** — a production-hardening slice (security headers, request limits, CORS, `/metrics`, CI supply-chain), a **durability slice** (PostgreSQL + async SQLAlchemy over asyncpg, Alembic migrations, UUIDv7 IDs, Python 3.14, `pg_advisory_xact_lock` atomicity, `WEB_CONCURRENCY` multi-worker, zstd response compression), a **durable transactional outbox** (events staged in the write's transaction, delivered at-least-once by an in-process relay — see the Events convention below), and **workflow guards / WIP-limits** (`meta`-declared role guards + state occupancy caps, enforced by the engine via a `TransitionContext`). The locked design lives in `docs/PRD.md`, `docs/FRD.md`, and `docs/TIS.md` — treat those three as the source of truth (TIS for code shape, FRD for contracts, PRD for scope). `docs/Python_Assignment.pdf` is the original brief.

## Code cleanliness

- ❌ No backward-compatibility shims, deprecated wrappers, or commented-out blocks. Delete obsolete code immediately when models change.
- ❌ No files/classes/methods with `enhanced`, `improved`, `optimized`, `new`, `clean` prefixes or suffixes. Update the original instead of creating a duplicate.
- ❌ No temporal markers in code or tests — no `(NEW)`, `(UPDATED)`, `(FIXED)`, `(OLD)`, no version suffixes, no changelog-style annotations. Code describes **what** something does; git history records **when**.
- ❌ No `TODO`/`FIXME` comments — implement it now, or open an issue. The TIS is the backlog.
- ❌ No placeholder implementations — no stub functions, empty classes, or dummy return values. If a dependency (enum, exception, helper) is missing, create it.
- ❌ No inline imports. All imports at module top level. An inline import is a circular-dependency design smell — fix the cycle (move the logic to the correct layer) instead of hiding it. *Exception:* test files may use inline imports for test-specific mocks only.

## Coding style

- **Type hints are mandatory.** `pyright` strict mode is configured for `app/` and `tests/`.
- **Early returns, flat > nested.** Validate inputs at function start, raise/return immediately on failure. Cap nesting at 2–3 levels; if you exceed it, extract a helper.
- **One Obvious Way.** No multiple ways to do the same thing, no convenience aliases, no alternative input formats — if the contract says JSON array, reject comma-separated. Use framework defaults (Pydantic/FastAPI) instead of custom parsing.
- **Naming.** `snake_case` for functions/vars, `CamelCase` for classes, `UPPER_SNAKE_CASE` for constants.
- **Async everywhere.** Routes, service-layer methods, and the SQLModel repository are all `async def` (async SQLAlchemy over asyncpg). `.add()` stays sync; every `.get/.scalar/.exec/.commit/.rollback/.delete` is awaited.

## Always validate after changes

```bash
uv run ruff check --fix path/to/file.py
uv run pyright path/to/file.py
```

For wider sweeps before declaring done: `uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest`.

## Tooling and commands

Project is managed by **uv** (Python 3.14). Always run commands through `uv run` so the project virtualenv is used. **Never use `pip` directly. Never activate the venv manually** (`source .venv/bin/activate`) — `uv run` handles it.

```
uv sync                                  # install runtime + dev deps from uv.lock
uv run pre-commit install                # one-time, wires local hooks
uv run uvicorn app.main:app --reload     # local dev server — reload (needs Postgres + alembic upgrade head)

uv run pytest                            # full test run with coverage gate (--cov-fail-under=80)
uv run pytest app/services/tasks/tests   # unit tests only (fast, no FastAPI/DB)
uv run pytest tests/integration          # integration (in-process FastAPI + Postgres via testcontainers)
uv run pytest tests/contract             # repository ABC conformance, parametrized over impls
uv run pytest -k test_name               # single test by substring
uv run pytest path/to/test_file.py::test_fn

uv run ruff check . && uv run ruff format --check .
uv run pyright                           # strict, configured in pyproject.toml
uv run bandit -c pyproject.toml -r app   # severity ≥ medium fails CI
uv run pre-commit run --all-files

hurl --test --report-html reports/hurl tests/hurl/*.hurl   # E2E against running container
```

`pytest` picks up tests from both `app/services/` (feature-local unit tests) and `tests/` (cross-boundary), per `[tool.pytest.ini_options]` in `pyproject.toml`. Coverage omits `app/main.py`.

## Architecture — feature-first hexagonal

Each feature under `app/services/<feature>/` owns its full vertical slice and exposes an explicit `interfaces.py` ABC at the feature root for swappable adapters. The textbook Cosmic-Python ceremony (separate `ports/`, `Protocol` typing, distinct domain entity apart from the SQLModel row, `import-linter`) is deliberately **not** used in Phase 1.

Layered import rules — enforced by review, not tooling:

1. `app/services/<feature>/domain/**` may import stdlib, `pydantic`, `sqlmodel`, `app/core/*`. **No `fastapi`.**
2. `app/services/<feature>/application/**` may import `domain/`, `interfaces.py`, the feature-root `serialization.py` (where one exists — a cross-layer seam like `interfaces.py`), `app/core/*` shared-kernel types (e.g. `core/event_bus.Event`, which the service builds and hands to the repo), and a **sibling feature's** `interfaces.py`/`domain/` types for cross-feature seams. **No `infrastructure/`, no `fastapi`.**
3. `app/services/<feature>/infrastructure/**` may import everything in the feature plus DB helpers from `app/core/`.
4. `app/services/<feature>/api/**` is the only feature-internal place that touches `fastapi` — except the DI wiring file (see below).
5. `app/core/**` must not import from any individual service.

**Documented exception to rule 4:**

- `app/services/<feature>/dependencies.py` is the feature's DI wiring — it composes repository → service for the router and may import `fastapi.Depends`/`Query`. It is api-adapter wiring co-located at the feature root, not application logic. Cross-feature data access follows the owning-repository rule: a service receives the *other* feature's repository **interface** via its constructor (e.g. `TaskService(..., workflows=...)`), and only `dependencies.py` may import the other feature's concrete repository — never its `dependencies.py`, and always constructed from the same request session.

The `Task` SQLModel row **is** the domain entity (`table=True`). There is no separate ORM/domain split in Phase 1.

## Key conventions

- **Uniqueness key.** `Task.title_key = title.strip().casefold()` is the canonical unique column; `title` is preserved verbatim for display. Duplicate-title detection always goes through `title_key`, never `title`. `Tag.name_key` follows the identical rule — any tag lookup goes through `name_key`.
- **Tags.** A separate feature slice (`app/services/tags/`) owning both the `tags` vocabulary and the `task_tags` join. Tags are set **inline on the task body** (`POST`/`PUT`/`PATCH /v1/tasks` accept `tags: [...]`) — there is no `/v1/tasks/{id}/tags` sub-resource, and the list is **replaced, never merged**. Unknown names are created on use, so there is no tag-creation endpoint either; `DELETE /v1/tags/{id}` refuses with 409 `tag_in_use` while tasks still hold it, mirroring the workflow strand guard. `?tag=` on `GET /v1/tasks` repeats to **narrow** (AND) — deliberately unlike `?status=`, which repeats to widen, because a task has one status but many tags. `TaskService` reaches tags through `TagRepositoryInterface` on the same request session; only `tasks/dependencies.py` may import the concrete repo.
- **Workflow-governed status.** `Task.status` is a plain `str` validated against the **active workflow definition** (`app/services/workflows/`, seeded any→any over `new`/`in_progress`/`completed`). Unknown state in a body → 422 `unknown_status`; illegal move / non-entry create → 409 `invalid_transition`; `PUT /v1/workflow` rejects definitions stranding occupied states (409 `workflow_states_in_use`). Unknown *filter* values on `GET /v1/tasks` return 200 with no matches. Never reintroduce a status enum — states are runtime data.
- **Workflow guards (`meta`-declared, engine-enforced).** A transition's `{"roles": [...]}` guards a move (actor must hold one, else 403 `transition_forbidden`); a state's `{"wip_limit": N}` caps occupancy (entering a full state → 409 `wip_limit_exceeded`, best-effort under the shared lock). The engine reads them via a `TransitionContext(roles, occupancy)` the service builds per write — `roles` from the **provisional, unauthenticated `X-Roles` header** (a stand-in until auth lands; the auth principal replaces the seam with no engine change), `occupancy` from `count_by_status()`, fetched only when `engine.needs_occupancy(from_status=…, to_status=…)` says this write can actually enter a capped state. Both guard values are validated at the `PUT /v1/workflow` boundary. Meta keys the engine reads (`completes`, `wip_limit`, `roles`) are named `*_META_KEY` constants in `workflows/domain/models.py`; the rest of `meta` stays uninterpreted.
- **UTC everywhere.** All timestamps are `datetime.now(UTC)` and stored timezone-aware. The Docker image sets `TZ=UTC`. Naïve datetimes are a bug — see FRD §2.4.
- **Error envelope.** Every non-2xx response is `{"error": {"code", "message", "details", "request_id"}}`. Feature-domain exceptions (`DuplicateTaskError`, `TaskNotFoundError`, `EmptyUpdateError`) live in `app/services/tasks/errors.py` and inherit from `AppError` base classes in `app/core/errors.py`; `ReadOnlyFieldError` lives in `app/core/errors.py` itself because server-owned-field rejection is a framework-level concern raised by the global validation handler, not by feature code. All paths are converted by a single global handler. See FRD §3.4 and §4. **Never inherit from plain `Exception`** — that bypasses the central handler and returns 500. In `dev` mode only, raisers may pass `original_error=` and the envelope's `details.cause` will surface the underlying exception (gated by `settings.expose_stack_traces`).
- **Error file naming.** `errors.py` at the feature root, never `exceptions.py`.
- **Events are delivered by a transactional outbox.** The write stages its events into the `outbox` table in the **same transaction** as the row change (`repo.persist(task, events=...)` / `repo.remove(task, events=...)`), so they are never lost to a crash. An in-process relay (`app/core/outbox.py`, started/stopped in the lifespan) delivers each pending event to the `EventBus` listeners **at-least-once**, off the request path so they never block the response, then marks it published; a failed delivery retries (`retry_count`/`last_error`) and, past `outbox_max_retries`, is stamped `dead_lettered_at` — a **terminal** marker, so the row leaves the poll's partial index for good and re-driving it is a deliberate operator action (clear the stamp + `retry_count`), never a side effect of retuning the ceiling. Only **delivered** rows are pruned (after `outbox_retention_days`, default 7), in bounded batches. Only the two ends of a failure log at alert level — `outbox_delivery_failed` on the first, `outbox_dead_lettered` on death; the retries between are debug. Listeners must be **idempotent** (dedupe on `event.id`). The service no longer touches the bus — it *builds* events and hands them to the repo; the relay is the sole delivery path. Six events: `TaskCreated`, `TaskUpdated`, `TaskStatusChanged`, `TaskCompleted`, `TaskDeleted`, `WorkflowUpdated`. `TaskCompleted` is a convenience fanout from `TaskStatusChanged` when the entered state's definition carries `"completes": true` (seed marks `completed`).
- **Server-owned fields** (`id`, `created_at`) on `PUT`/`PATCH` bodies must be rejected with `ReadOnlyFieldError` (422 `read_only_field`).
- **PATCH with no fields** → `EmptyUpdateError` (422 `empty_update`). A PATCH that supplies fields but changes nothing returns 200 and emits **no** events.
- **Request-ID middleware** generates a UUIDv4 when `X-Request-ID` is absent, binds it to the structlog context, and echoes it on the response. Lives in `app/core/middleware.py`.

## Configuration

`pydantic-settings` loads a shared `.env` base layer plus a per-environment `.env.<APP_ENV>` overlay, the overlay winning on any key both set. `APP_ENV ∈ {dev, test, qa, prod}`, defaults to `dev`. Process env vars **override** file contents (k8s/CI win). `.env.example` is the only `.env*` checked in; `.dockerignore` keeps `.env*` out of the image. The `APP_ENV → (log_level, json_logs, expose_stack_traces)` matrix is in FRD §6.3.

## Postgres specifics

Persistence is **PostgreSQL** via async SQLAlchemy (`create_async_engine` + `async_sessionmaker(class_=AsyncSession, expire_on_commit=False)`) over **asyncpg**. `app/core/database.py` exposes a re-bindable `configure(url, *, poolclass=None)` + `get_sessionmaker()` so tests (testcontainers) can point the app at a throwaway Postgres after import; `expire_on_commit=False` is load-bearing (post-commit `snapshot()` reads must not lazy-refresh). **Alembic owns the production schema** (`alembic upgrade head` runs at deploy via the Docker entrypoint, before uvicorn) — the lifespan no longer creates tables; it seeds the workflow row, starts the outbox relay, and on shutdown stops the relay and disposes the engine. Tests build the schema via the conftest fixture (`init_schema()` + TRUNCATE + reseed). Atomicity of the workflow-vs-status critical section is held by a transaction-scoped **reader/writer** advisory lock via `acquire_workflow_guard(shared=...)`: task-status writes take the SHARED form (`pg_advisory_xact_lock_shared`, so they run concurrently across workers), while `PUT /v1/workflow` + seed take the EXCLUSIVE form — making multi-worker (`WEB_CONCURRENCY`) both safe and scalable. See TIS §7.1, §8.7, §8.8.

## Test layout — the split rule

> Can this test run with only my feature module imported? If yes → unit, lives in `app/services/<feature>/tests/`. If it needs `from app.main import app`, real HTTP, or another feature → it crosses a boundary and lives under `tests/`. *Clarification:* feature-local unit tests may import a **sibling feature's `interfaces.py`/`domain/`** solely to build in-memory fakes (e.g. `FakeWorkflowRepo` in the tasks unit tests) — that does not make them cross-boundary.

Hurl scenarios (`tests/hurl/*.hurl`) run against the **running container**, not the in-process app. Reports go to `reports/hurl/` (gitignored except for `.gitkeep`). Schemathesis (`tests/e2e/`) is optional in Phase 1, mandatory in Phase 2.

Integration tests use `httpx.AsyncClient` with `ASGITransport`. Note: `ASGITransport` does **not** run FastAPI's lifespan automatically — wrap the test client setup in an explicit `async with LifespanManager(app)` (or equivalent) so startup hooks fire.

## Acceptance gates (Phase 1 done = all true)

Every API row in FRD §3.1 has ≥1 integration test; every error `code` in FRD §4 has ≥1 envelope-asserting test; every event in FRD §5.1 has ≥1 service-layer unit test asserting it fires under right conditions *and does not fire* under wrong ones; contract tests pass against every concrete repository; the documented Hurl scenarios pass against the container; `ruff`, `ruff format --check`, `pyright`, `bandit`, and `pytest --cov-fail-under=80` all green; the Docker image builds and `/healthz` returns 200.

## Memory and prior context

Project memory references: PRD/FRD/TIS were aligned to v1.1 feature-first hex on 2026-05-14 (sessions S674–S680). Phase 1 shipped, workflow-as-a-service landed (commit `a6a0de4`), and the Phase-2 durability slice (Postgres/async/Alembic/UUIDv7/Python 3.14/advisory locks/zstd) is the most recent work — the running log lives in the project memory `phase_status.md`.
