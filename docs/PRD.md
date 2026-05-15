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

- `Task` domain entity with: numeric ID, unique title, optional description, status (`new` / `in_progress` / `completed`), priority (1–5), `created_at` timestamp.
- HTTP API mounted under `/v1` exposing **Create, List, Get, Update (PUT and PATCH), Delete** for tasks.
- Query parameters on `GET /v1/tasks` for **filter by status**, **sort by priority**, and **offset/limit pagination**.
- **In-memory** repository (default adapter: SQLite `:memory:` via SQLModel) behind a pluggable Repository port.
- **Domain Event Bus** publishing `TaskCreated`, `TaskUpdated`, `TaskStatusChanged`, `TaskCompleted`, `TaskDeleted`. Ships with one listener: a structured-log subscriber.
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
| **The Systems Architect** | Assurance that swapping the in-memory store for Postgres later does not touch the domain layer.        |
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
5. `ruff check` and `mypy` pass with zero errors in CI.
6. The README in the repository explains: project structure, how to run locally (with and without Docker), how to run tests, how to override config via `.env`.
7. A fresh checkout to a running service takes one command (`docker compose up` or `uv run uvicorn …`) and no manual setup beyond that.

## 9. Non-Functional Requirements

| Category             | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                         |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Performance          | P95 latency for any single-task endpoint < 50 ms on a developer laptop with the default in-memory store.                                                                                                                                                                                                                                                                                                                            |
| Reliability          | The service must start with an empty store and remain operational; no read should ever leak storage-layer exceptions to the API consumer.                                                                                                                                                                                                                                                                                           |
| Observability        | Every request produces at least one structured log line including `request_id`, `method`, `path`, `status`, and `duration_ms`.                                                                                                                                                                                                                                                                                                      |
| **Time consistency** | The PDF establishes that _"the team is spread across multiple time zones."_ Every timestamp the service stores, returns, or logs must therefore be **timezone-aware UTC** — never naive `datetime`, never local time. API responses serialize timestamps as RFC 3339 with a `Z` suffix (`2026-05-14T13:01:42Z`). Clients are expected to convert to local time at the presentation edge; the service is the single source of truth. |
| Portability          | The service must run on Linux and macOS, Python 3.13+. No OS-specific dependencies.                                                                                                                                                                                                                                                                                                                                                 |
| Maintainability      | The feature-first hex layout (FRD §1) must be preserved — adapters never short-circuit the application or domain layers.                                                                                                                                                                                                                                                                                                            |

## 10. Assumptions

- Phase 1 callers are trusted internal services or developers; no abuse-protection (rate limiting, captcha) is needed yet.
- Task data is not sensitive and may live in memory across restarts (data loss on restart is acceptable for Phase 1).
- The service runs as a single instance in Phase 1; concurrency concerns beyond a single uvicorn worker are out of scope.
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

Captured here as planning seeds only; detailed designs and TIS revisions happen when each item is scheduled.

- Persistent storage adapter (PostgreSQL / MySQL).
- Cache layer (Redis, Memcached)
- Schema migrations via **Alembic**.
- Rate limiting via **slowapi**.
- **Users module** - tasks created by user & assign to a user.
- **RBAC** authentication & authorization module (OIDC + role/permission matrix).
- **Tags module** - tasks can have one or multiple tags.
- **Workflow Phase module** — make the currently hard-coded statuses (`new`, `in_progress`, `completed`) into a configurable entity with its own endpoints and per-phase business rules.
- **Attachment support** - Tasks can have file attachment support.
- Notification adapter for Slack subscribing to `TaskStatusChanged` / `TaskCompleted`.
- `/metrics` endpoint (Prometheus).
- Audit log and soft delete.
