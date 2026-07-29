# Graph Report - .  (2026-07-28)

## Corpus Check
- 61 files · ~34,342 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 805 nodes · 2041 edges · 67 communities (47 shown, 20 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 230 edges (avg confidence: 0.57)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Integration Test Harness|Integration Test Harness]]
- [[_COMMUNITY_Task Service & Enforcement|Task Service & Enforcement]]
- [[_COMMUNITY_Database & DI Wiring|Database & DI Wiring]]
- [[_COMMUNITY_Workflow Definition Domain|Workflow Definition Domain]]
- [[_COMMUNITY_Workflow Concepts (Docs)|Workflow Concepts (Docs)]]
- [[_COMMUNITY_Workflow Serialization & Seed|Workflow Serialization & Seed]]
- [[_COMMUNITY_Time & Interface Utilities|Time & Interface Utilities]]
- [[_COMMUNITY_Task Domain Entity|Task Domain Entity]]
- [[_COMMUNITY_Workflow Service & Versioning|Workflow Service & Versioning]]
- [[_COMMUNITY_Settings & Environment Config|Settings & Environment Config]]
- [[_COMMUNITY_HTTP API Router|HTTP API Router]]
- [[_COMMUNITY_Error Envelope Core|Error Envelope Core]]
- [[_COMMUNITY_Error Envelope Tests|Error Envelope Tests]]
- [[_COMMUNITY_List & Pagination Tests|List & Pagination Tests]]
- [[_COMMUNITY_Request-ID & Logging Tests|Request-ID & Logging Tests]]
- [[_COMMUNITY_App Factory & Lifespan|App Factory & Lifespan]]
- [[_COMMUNITY_Event Bus Core|Event Bus Core]]
- [[_COMMUNITY_Logging & Middleware|Logging & Middleware]]
- [[_COMMUNITY_Event Listeners|Event Listeners]]
- [[_COMMUNITY_Spec Document Suite|Spec Document Suite]]
- [[_COMMUNITY_Pre-commit Hooks|Pre-commit Hooks]]
- [[_COMMUNITY_Schemathesis E2E|Schemathesis E2E]]
- [[_COMMUNITY_Graphify Tooling|Graphify Tooling]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Async Alignment Rationale|Async Alignment Rationale]]
- [[_COMMUNITY_Polish Plan Note|Polish Plan Note]]
- [[_COMMUNITY_Assignment Brief|Assignment Brief]]
- [[_COMMUNITY_CRUD Requirement|CRUD Requirement]]
- [[_COMMUNITY_Repository Requirement|Repository Requirement]]
- [[_COMMUNITY_README Requirement|README Requirement]]
- [[_COMMUNITY_Task Entity Requirement|Task Entity Requirement]]
- [[_COMMUNITY_Testing Requirement|Testing Requirement]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Project Root|Project Root]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]
- [[_COMMUNITY_Package Marker|Package Marker]]

## God Nodes (most connected - your core abstractions)
1. `Workflow` - 73 edges
2. `Task` - 69 edges
3. `assert_error()` - 65 edges
4. `TaskService` - 62 edges
5. `TaskRepositoryInterface` - 52 edges
6. `RecordingBus` - 40 edges
7. `State` - 37 edges
8. `create_task()` - 31 edges
9. `ValidationError` - 29 edges
10. `TaskSortField` - 28 edges

## Surprising Connections (you probably didn't know these)
- `test_task_sort_field_values_match_task_columns()` --indirect_call--> `Task`  [INFERRED]
  tests/contract/test_task_repository_interface.py → app/services/tasks/domain/models.py
- `Title Uniqueness (title_key)` --semantically_similar_to--> `Strand Guard`  [INFERRED] [semantically similar]
  docs/FRD.md → app/services/workflows/MODULE.md
- `task-service compose service` --references--> `liveness()`  [EXTRACTED]
  docker/docker-compose.yaml → app/core/health.py
- `test_settings_log_level_validation()` --indirect_call--> `ValidationError`  [INFERRED]
  tests/integration/core/test_config.py → app/core/errors.py
- `test_settings_api_prefix_validation()` --indirect_call--> `ValidationError`  [INFERRED]
  tests/integration/core/test_config.py → app/core/errors.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Post-Commit Domain Event Fan-Out** — docs_tis_task_service, docs_frd_event_bus, docs_tis_background_tasks_fanout, docs_frd_task_created, docs_frd_task_deleted [INFERRED 0.85]
- **Workflow Definition Update Pipeline (validate -> strand guard -> append version)** — app_services_workflows_module_workflow_service, app_services_workflows_module_collect_all_errors, app_services_workflows_module_strand_guard, app_services_workflows_module_append_only_versioning, docs_frd_workflow_updated [INFERRED 0.90]
- **Task Status-Change Enforcement Against Active Workflow** — docs_tis_task_service, docs_frd_workflow_as_runtime_data, app_services_tasks_module_invalid_transition_error, app_services_workflows_module_completes_meta, docs_frd_task_completed [INFERRED 0.85]

## Communities (67 total, 20 thin omitted)

### Community 0 - "Integration Test Harness"
Cohesion: 0.06
Nodes (81): Response, assert_error(), create_task(), Any, CreateTask, Factory: ``await create_task(title, priority=3)`` → new task id., Assert the standard error envelope; return the parsed ``error`` block., AsyncClient (+73 more)

### Community 1 - "Task Service & Enforcement"
Cohesion: 0.09
Nodes (35): TaskListParams, Any, BackgroundTasks, Same-state writes are no-moves; anything else needs a defined transition., A status that is no state at all is a validation error, not a refusal., The task plus the definition-legal transitions out of its state., TaskService, TaskSortField (+27 more)

### Community 2 - "Database & DI Wiring"
Cohesion: 0.05
Nodes (45): Session, session_factory(), get_session(), Session, Contract knobs for the tasks feature — closed string sets and field bounds., get_task_service(), EventBusDep, SessionDep (+37 more)

### Community 3 - "Workflow Definition Domain"
Cohesion: 0.05
Nodes (50): _any_to_any(), Seed-equivalent: three states, all entries, every directed pair legal., Single entry, one forward path: new -> in_progress -> completed., _strict(), Any, TransitionTable, The workflow definition: which states exist and which named moves are legal.  St, Full transitions leaving a state — what a UI renders as buttons. (+42 more)

### Community 4 - "Workflow Concepts (Docs)"
Cohesion: 0.05
Nodes (60): CI Pipeline, InvalidTransitionError (409 invalid_transition), MUTABLE_FIELDS, Append-Only Versioned Storage, Behavior-Identical Seed, Collect-All-Errors Document Boundary, completes-meta Flag (COMPLETES_META_KEY), WorkflowEngine Not Ported (+52 more)

### Community 5 - "Workflow Serialization & Seed"
Cohesion: 0.07
Nodes (53): A workflow definition failed validation; ``errors`` lists every problem found., WorkflowValidationError, default_workflow(), The behavior-identical default: three states, any → any.      Every state is ``i, _extract_meta(), _parse_document(), _parse_state(), _parse_states() (+45 more)

### Community 6 - "Time & Interface Utilities"
Cohesion: 0.08
Nodes (33): ABC, ensure_utc(), iso_z(), datetime, RFC 3339 in UTC with the ``Z`` suffix — the wire format for timestamps., Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC., AppError, Any (+25 more)

### Community 7 - "Task Domain Entity"
Cohesion: 0.07
Nodes (14): Any, Self, Return ``(stripped_title, title_key)``; raise ``ValueError`` if empty., Build a Task from caller input, applying normalisation invariants., Detached, revalidated copy for event payloads., Overwrite every mutable field; ``title_key`` is recomputed from ``title``., Apply a partial update; raise ``ValueError`` for any non-mutable key., _new() (+6 more)

### Community 8 - "Workflow Service & Versioning"
Cohesion: 0.10
Nodes (19): Any, BackgroundTasks, Validate, strand-check, and store a new definition version.          The usage-c, WorkflowUpdated, bt(), bus(), FakeWorkflowRepo, Any (+11 more)

### Community 9 - "Settings & Environment Config"
Cohesion: 0.10
Nodes (21): Effective numeric log level; explicit ``LOG_LEVEL`` overrides the env default., Settings, Environment, OrderDirection, liveness(), JSONResponse, SessionDep, readiness() (+13 more)

### Community 10 - "HTTP API Router"
Cohesion: 0.17
Nodes (22): create_task(), delete_task(), get_task(), list_tasks(), patch_task(), BackgroundTasks, replace_task(), task_transitions() (+14 more)

### Community 11 - "Error Envelope Core"
Cohesion: 0.25
Nodes (16): ConflictError, _envelope(), _envelope_from_app_error(), ErrorCode, NotFoundError, Error code enum, ``AppError`` hierarchy, and global exception handlers., ReadOnlyFieldError, ValidationError (+8 more)

### Community 12 - "Error Envelope Tests"
Cohesion: 0.20
Nodes (17): FastAPI, register_exception_handlers(), MonkeyPatch, _crash_client(), AsyncClient, Exception, Throwaway FastAPI app whose ``/boom`` route raises ``error``; yields a wired Asy, FRD §4: exceptions outside the AppError hierarchy must still produce the envelop (+9 more)

### Community 13 - "List & Pagination Tests"
Cohesion: 0.24
Nodes (17): AsyncClient, Free-form states: an unknown filter value matches nothing (200 []), it is not a, Seeded priorities are 5,3,2,1 — offset=1, limit=2 desc must return the middle wi, SQLite binds offset as INT64 — an unbounded int overflows the driver, not valida, _seed(), test_list_default_sort_is_priority_desc(), test_list_empty_returns_zero_total(), test_list_filter_by_status_multivalue() (+9 more)

### Community 14 - "Request-ID & Logging Tests"
Cohesion: 0.21
Nodes (13): Any, AsyncClient, MonkeyPatch, Replaces ``structlog.BoundLogger`` for tests — captures calls and bound contextv, Each request must emit exactly one ``http_request`` access log with method/path/, 4xx responses produced by exception handlers must still log via the same access, _RecordingLogger, test_middleware_emits_one_http_request_log_per_request() (+5 more)

### Community 15 - "App Factory & Lifespan"
Cohesion: 0.24
Nodes (11): APIRoute, create_app(), custom_unique_id(), lifespan(), FastAPI, Idempotent: called from both app lifespan and the test schema reset., seed_workflow_if_missing(), client() (+3 more)

### Community 16 - "Event Bus Core"
Cohesion: 0.22
Nodes (9): get_event_bus(), Request, Event, EventBus, BackgroundTasks, log_event(), register_listeners(), BaseModel (+1 more)

### Community 17 - "Logging & Middleware"
Cohesion: 0.20
Nodes (6): Request, Response, Generate/propagate ``X-Request-ID``, bind it to structlog, and emit one access l, RequestIDMiddleware, BaseHTTPMiddleware, RequestResponseEndpoint

### Community 18 - "Event Listeners"
Cohesion: 0.32
Nodes (5): In-process pub/sub event bus; listeners run via FastAPI ``BackgroundTasks`` afte, log_event(), Event, EventBus, register_listeners()

### Community 19 - "Spec Document Suite"
Cohesion: 0.67
Nodes (7): Tasks Module Index, Workflows Module Index, CLAUDE.md Project Instructions, Functional Requirements Document (FRD), Product Requirements Document (PRD), Technical Implementation Specification (TIS), Internal Task Service README

### Community 20 - "Pre-commit Hooks"
Cohesion: 0.40
Nodes (5): bandit security hook, file-hygiene hooks, pre-commit hook configuration, ruff + ruff-format hooks, uv-lock-check local hook

### Community 21 - "Schemathesis E2E"
Cohesion: 0.50
Nodes (3): Case, Any, test_no_5xx_and_schema_conformance()

## Knowledge Gaps
- **20 isolated node(s):** `Phase 1 polish plan (Annotated + async)`, `uv`, `task-service compose service`, `Python Assignment Brief`, `Task Entity Requirement (6 properties)` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **20 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Task` connect `Task Service & Enforcement` to `HTTP API Router`, `Database & DI Wiring`, `Task Domain Entity`?**
  _High betweenness centrality (0.126) - this node is a cross-community bridge._
- **Why does `Workflow` connect `Workflow Definition Domain` to `Workflow Service & Versioning`, `Task Service & Enforcement`, `Workflow Serialization & Seed`, `Time & Interface Utilities`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `assert_error()` connect `Integration Test Harness` to `Workflow Serialization & Seed`, `Error Envelope Core`, `Error Envelope Tests`, `List & Pagination Tests`, `App Factory & Lifespan`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `Workflow` (e.g. with `TaskService` and `FakeRepo`) actually correct?**
  _`Workflow` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `Task` (e.g. with `TaskService` and `TaskCompleted`) actually correct?**
  _`Task` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `TaskService` (e.g. with `ValidationError` and `TaskListParams`) actually correct?**
  _`TaskService` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `TaskRepositoryInterface` (e.g. with `TaskService` and `SQLModelTaskRepository`) actually correct?**
  _`TaskRepositoryInterface` has 18 INFERRED edges - model-reasoned connections that need verification._
