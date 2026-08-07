# 📄 Product Requirements Document (PRD)

**Project Name:** Internal Task Service
**Document Version:** 1.0
**Status:** Phase 1 Implementation

---

## 1. Problem Statement

The team is small, fast-moving, and distributed across multiple time zones. Specifications and tasks are exchanged in online meetings and scattered afterwards across sticky notes, chat messages, and personal to-do lists. There is no single source of truth for "what we agreed to do," which causes:

- Lost or duplicated work items.
- Confusion in stand-ups about which task is being discussed (multiple people referring to the same idea by different names).
- No ability to filter by progress or prioritize across the team.

During a stand-up, the Product Owner asked for **"a simple task service. Something internal. Clean. We'll build more on top of it later."** This PRD scopes the first iteration of that service.

## 2. Vision

A clean, internal HTTP service that owns the canonical list of team tasks. Phase 1 is deliberately small and in-memory; the architecture is decoupled so that future phases can swap storage, add notifications, or extend the workflow without rewriting the core domain.

## 3. Strategic Objectives

| #   | Objective                                                             | Why it matters                                                                 |
| --- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| O1  | **Centralize** task state behind one REST API.                        | Eliminate "where is the canonical version of this task?"                       |
| O2  | **Prevent duplicates** by enforcing unique titles.                    | Removes confusion in stand-ups, per the PO's brief.                            |
| O3  | **Keep the core decoupled** from frameworks and storage.              | "We'll build more on top of it later" — Phase 2 work must not rewrite Phase 1. |
| O4  | **Operate predictably** with structured logs and standardized errors. | The team needs to debug across time zones without sitting next to the box.     |
| O5  | **Ship with tests and a clear README.**                               | The assignment requires it; future contributors join without ramp-up cost.     |

## 4. In Scope (Phase 1)

- `Task` domain entity with: UUID (UUIDv7) ID, unique title, optional description, status (governed by the active workflow definition; seeded states `new` / `in_progress` / `completed`), priority (1–5), `created_at` timestamp.
- HTTP API mounted under `/v1` exposing **Create, List, Get, Update (PUT and PATCH), Delete** for tasks.
- Query parameters on `GET /v1/tasks` for **filter by status**, **sort by priority**, and **offset/limit pagination**.
- **PostgreSQL** repository (async SQLAlchemy over asyncpg, via SQLModel) behind a pluggable Repository port. (Phase 1 shipped an in-memory SQLite adapter; Phase 2 swapped it for Postgres — the port held.)
- **Domain Event Bus** publishing `TaskCreated`, `TaskUpdated`, `TaskStatusChanged`, `TaskCompleted`, `TaskDeleted`, and `WorkflowUpdated`. Ships with structured-log subscribers for all of them.
- **Operational endpoints** `/healthz` and `/readyz`, plus a Request-ID middleware that propagates `X-Request-ID` into every log line.
- **Environment-aware configuration** via per-env `.env.*` files + `pydantic-settings` (`APP_ENV` ∈ {dev, test, qa, prod} drives log level and verbosity).
- **Test suite** with ≥80% coverage (pytest + httpx).
- **Docker image** and developer README explaining structure, run, and test.

## 5. Out of Scope (Phase 1)

The following are deliberately excluded from Phase 1 and recorded here so future contributors do not assume they were forgotten:

- Authentication and authorization (the service is internal; access control is delegated to the deployment environment for Phase 1).
- External notification adapters (Slack, email).
- Persistent storage (PostgreSQL, etc.).
- Prometheus `/metrics` endpoint.
- Front-end UI.
- Multi-tenant or per-user scoping of tasks.
- Audit log / soft-delete / task history.

## 6. User Personas

| Persona                   | Needs                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------ |
| **The Developer**         | A predictable REST API to script task creation from CLI tools and CI jobs.                             |
| **The Product Owner**     | Confidence that no two tasks have the same title and that priorities follow the agreed 1–5 scale.      |
| **The Systems Architect** | Confirmation that the swap to Postgres left the domain layer untouched — the port held.                |
| **The On-Call Engineer**  | A `/healthz` that returns the truth, structured logs with a request ID, and standardized error bodies. |

## 7. User Stories (Phase 1)

| ID    | As a…     | I want to…                                                                           | So that…                                                                                         |
| ----- | --------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| US-01 | Developer | create a task via `POST /v1/tasks` with title, optional description, and priority    | I can capture an action item the moment it is agreed upon.                                       |
| US-02 | Developer | list all tasks, optionally filtered by status and sorted by priority                 | I can see what is open and what to work on next.                                                 |
| US-03 | Developer | fetch a single task by ID                                                            | I can deep-link to a specific item in chat.                                                      |
| US-04 | Developer | update a task fully (PUT) or partially (PATCH)                                       | I can flip status, bump priority, or rewrite the title without reconstructing the whole payload. |
| US-05 | Developer | delete a task                                                                        | We can clear out items that turned out to be invalid.                                            |
| US-06 | PO        | be prevented from creating two tasks with the same title (case-insensitive, trimmed) | Stand-ups stay free of "which 'fix bug' did you mean?"                                           |
| US-07 | Operator  | call `/healthz` and `/readyz`                                                        | The container orchestrator can route traffic correctly.                                          |
| US-08 | Operator  | correlate logs across requests via `X-Request-ID`                                    | I can debug a single failed call across components.                                              |

## 8. Success Criteria

The Phase 1 release is considered done when **all** of the following are true:

1. All endpoints listed in Section 4 are implemented and reachable behind `/v1`.
2. All Phase 1 user stories (US-01…US-08) pass automated integration tests.
3. Title uniqueness rule rejects duplicates with HTTP `409 Conflict` and a domain-typed error body.
4. Test coverage reported by `pytest --cov` is ≥ 80% on the `app/` package.
5. `ruff check` and `pyright` pass with zero errors in CI.
6. The README in the repository explains: project structure, how to run locally (with and without Docker), how to run tests, how to override config via `.env`.
7. A fresh checkout to a running service takes one command (`docker compose up` or `uv run uvicorn …`) and no manual setup beyond that.

## 9. Non-Functional Requirements

| Category             | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                         |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Performance          | P95 latency for any single-task endpoint < 50 ms on a developer laptop against a local Postgres instance.                                                                                                                                                                                                                                                                                                                            |
| Reliability          | The service must start with an empty store and remain operational; no read should ever leak storage-layer exceptions to the API consumer.                                                                                                                                                                                                                                                                                           |
| Observability        | Every request produces at least one structured log line including `request_id`, `method`, `path`, `status`, and `duration_ms`.                                                                                                                                                                                                                                                                                                      |
| **Time consistency** | The PDF establishes that _"the team is spread across multiple time zones."_ Every timestamp the service stores, returns, or logs must therefore be **timezone-aware UTC** — never naive `datetime`, never local time. API responses serialize timestamps as RFC 3339 with a `Z` suffix (`2026-05-14T13:01:42Z`). Clients are expected to convert to local time at the presentation edge; the service is the single source of truth. |
| Portability          | The service must run on Linux and macOS, Python 3.14+. No OS-specific dependencies.                                                                                                                                                                                                                                                                                                                                                 |
| Maintainability      | The feature-first hex layout (FRD §1) must be preserved — adapters never short-circuit the application or domain layers.                                                                                                                                                                                                                                                                                                            |

## 10. Assumptions

- Phase 1 callers are trusted internal services or developers; no abuse-protection (rate limiting, captcha) is needed yet.
- Task data is not sensitive. It is now durable in PostgreSQL and survives restarts (Phase 1's in-memory store, where loss on restart was acceptable, has been retired).
- The service supports multiple uvicorn workers (`WEB_CONCURRENCY`, default 1), made safe by Postgres transaction-scoped advisory locks; the Phase-1 single-instance assumption is lifted.
- The team is comfortable with Python, FastAPI, and `uv` as the dependency manager.

## 11. Risks

| Risk                                                                        | Likelihood | Impact | Mitigation                                                                                             |
| --------------------------------------------------------------------------- | ---------- | ------ | ------------------------------------------------------------------------------------------------------ |
| Scope creep into "real" notifications/auth before Phase 1 ships             | Med        | High   | Treat Section 5 as a hard contract; capture new ideas as Phase 2 issues, not Phase 1 work.             |
| Title-uniqueness rule frustrates users (e.g., reusing titles across cycles) | Low        | Low    | Document the rule clearly in the API; revisit in Phase 2 if it becomes a real pain point.              |
| In-memory store loses data on restart and surprises someone                 | Med        | Med    | README and OpenAPI description must call this out explicitly.                                          |
| Hexagonal layout overhead slows initial delivery                            | Low        | Med    | Keep ports minimal (one repository, one event bus) — do not invent ports for things we don't have yet. |

## 12. Roadmap

### Phase 1 — Internal MVP (this PRD)

FastAPI + SQLModel (`:memory:`) + Internal Event Bus + structured logs + Docker.

### Phase 2 — Production-ready (future considerations)

Captured here as planning seeds only; detailed designs and TIS revisions happen when each item is scheduled. This list is the **single source of truth** for the product roadmap — FRD defers to it; TIS §10.1 owns any Phase 2 tooling considerations (e.g., `import-linter` reintroduction).

**Status: in progress — Phase 2 kicked off 2026-08-02** with a production-hardening slice: security headers, request size/time limits, config-driven CORS (off by default), the `/metrics` endpoint below, CI supply-chain scanning (Dependabot / Trivy / `pip-audit`), and Schemathesis gated in CI (TIS §10.1). A durability slice followed on 2026-08-03: persistent PostgreSQL 17 storage (async SQLAlchemy over asyncpg), Alembic migrations run at deploy via the Docker entrypoint, UUIDv7 public task IDs (stdlib `uuid.uuid7()`), the Python 3.14 upgrade, `WEB_CONCURRENCY` multi-worker support made safe by transaction-scoped advisory locks (`pg_advisory_xact_lock`), and a negotiated zstd response-compression middleware (Python 3.14 stdlib `compression.zstd`). Items marked ✅ are delivered.

- **Persistent storage adapter** — ✅ *delivered 2026-08-03* (PostgreSQL 17 via async SQLAlchemy over asyncpg, replacing the in-memory SQLite store; UUIDv7 public task IDs via stdlib `uuid.uuid7()`; `WEB_CONCURRENCY` multi-worker support made safe by transaction-scoped `pg_advisory_xact_lock`).
- Cache layer (Redis, Memcached).
- Schema migrations via **Alembic** — ✅ *delivered 2026-08-03* (run at deploy via the Docker entrypoint).
- Rate limiting via **slowapi**.
- **Users module** — tasks created by and assigned to a user.
- **RBAC** authentication & authorization module (OIDC + role/permission matrix).
- **Tags module** — tasks can have one or multiple tags — ✅ *delivered 2026-08-07* (its own feature slice owning the `tags` vocabulary and the `task_tags` join; tags set inline on the task body, unknown names created on use, `GET /v1/tags` + `DELETE /v1/tags/{id}` refusing 409 while tasks still hold the tag, and a repeatable `?tag=` filter that narrows by default or widens with `?op=or`. Contract in FRD §2.6–2.7).
- **Workflow Phase module** — ✅ *delivered in Phase 1* (states/transitions as runtime data, `GET/PUT /v1/workflow`, transition enforcement); per-phase business rules ✅ *delivered 2026-08-04* (a transition's `{"roles": [...]}` guard → 403 `transition_forbidden`, a state's `{"wip_limit": N}` cap → 409 `wip_limit_exceeded`, both declared on the definition's open `meta` channel and enforced by the engine through a `TransitionContext`). The acting roles arrive on the provisional `X-Roles` header until authentication lands.
- **Attachment support** — tasks can have file attachments.
- Notification adapter for Slack subscribing to `TaskStatusChanged` / `TaskCompleted`.
- **`/metrics` endpoint** (Prometheus exposition format) — ✅ *delivered 2026-08-02* (via `prometheus-fastapi-instrumentator`; ops-only, excluded from the OpenAPI schema).
- **Audit log and soft delete** — non-destructive deletes, full mutation history per task.
- **Front-end SPA** consuming `/v1`.
