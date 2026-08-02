# Graph Report - .  (2026-07-29)

## Corpus Check
- 9 files · ~34,456 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 791 nodes · 1993 edges · 78 communities (54 shown, 24 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 222 edges (avg confidence: 0.57)
- Token cost: 145,207 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Task API Integration Tests|Task API Integration Tests]]
- [[_COMMUNITY_Task Service & Unit Tests|Task Service & Unit Tests]]
- [[_COMMUNITY_App Wiring & Error Envelope|App Wiring & Error Envelope]]
- [[_COMMUNITY_Workflow Service Layer|Workflow Service Layer]]
- [[_COMMUNITY_Error Taxonomy|Error Taxonomy]]
- [[_COMMUNITY_Workflow Definition Domain|Workflow Definition Domain]]
- [[_COMMUNITY_Config & Health|Config & Health]]
- [[_COMMUNITY_Task API Router & DTOs|Task API Router & DTOs]]
- [[_COMMUNITY_Task Repository Contract|Task Repository Contract]]
- [[_COMMUNITY_Workflow Repository & Storage|Workflow Repository & Storage]]
- [[_COMMUNITY_Task Write Path & Enforcement|Task Write Path & Enforcement]]
- [[_COMMUNITY_Task Model & Title Rules|Task Model & Title Rules]]
- [[_COMMUNITY_Workflow API & Timestamps|Workflow API & Timestamps]]
- [[_COMMUNITY_Task Repository (SQLModel)|Task Repository (SQLModel)]]
- [[_COMMUNITY_Task Listing & Filter Tests|Task Listing & Filter Tests]]
- [[_COMMUNITY_Project Docs & Core Concepts|Project Docs & Core Concepts]]
- [[_COMMUNITY_Task Model Mutation Tests|Task Model Mutation Tests]]
- [[_COMMUNITY_Workflow Serialization|Workflow Serialization]]
- [[_COMMUNITY_Workflow Endpoint Tests & Seed|Workflow Endpoint Tests & Seed]]
- [[_COMMUNITY_Request-ID Middleware Tests|Request-ID Middleware Tests]]
- [[_COMMUNITY_Workflow Domain Modules|Workflow Domain Modules]]
- [[_COMMUNITY_Task Sorting & Interfaces|Task Sorting & Interfaces]]
- [[_COMMUNITY_State & Transition Value Objects|State & Transition Value Objects]]
- [[_COMMUNITY_Database & Sessions|Database & Sessions]]
- [[_COMMUNITY_Task Construction Tests|Task Construction Tests]]
- [[_COMMUNITY_Workflow Query API|Workflow Query API]]
- [[_COMMUNITY_Workflow Design Concepts|Workflow Design Concepts]]
- [[_COMMUNITY_Pre-commit Hooks|Pre-commit Hooks]]
- [[_COMMUNITY_Hurl E2E & CI|Hurl E2E & CI]]
- [[_COMMUNITY_Dev Tooling|Dev Tooling]]
- [[_COMMUNITY_PRD & README|PRD & README]]
- [[_COMMUNITY_JSONResponse|JSONResponse]]
- [[_COMMUNITY_Request|Request]]
- [[_COMMUNITY_BackgroundTasks|BackgroundTasks]]
- [[_COMMUNITY_EventBus|EventBus]]
- [[_COMMUNITY_Behavior-Identical Seed|Behavior-Identical Seed]]
- [[_COMMUNITY_Workflows Module Index|Workflows Module Index]]
- [[_COMMUNITY_ConflictError|ConflictError]]
- [[_COMMUNITY_Async Alignment Rationale|Async Alignment Rationale]]
- [[_COMMUNITY_Phase 1 Polish Plan|Phase 1 Polish Plan]]
- [[_COMMUNITY_Python Assignment Brief|Python Assignment Brief]]
- [[_COMMUNITY_FastAPI CRUD Requirement|FastAPI CRUD Requirement]]
- [[_COMMUNITY_In-Memory Repo Requirement|In-Memory Repo Requirement]]
- [[_COMMUNITY_README Requirement|README Requirement]]
- [[_COMMUNITY_Task Entity Requirement|Task Entity Requirement]]
- [[_COMMUNITY_Testing Requirement|Testing Requirement]]
- [[_COMMUNITY_EventBusDep|EventBusDep]]
- [[_COMMUNITY_FixtureRequest|FixtureRequest]]
- [[_COMMUNITY_NotFoundError|NotFoundError]]
- [[_COMMUNITY_task-service|task-service]]
- [[_COMMUNITY_Response|Response]]
- [[_COMMUNITY_MonkeyPatch|MonkeyPatch]]
- [[_COMMUNITY_ValidationError|ValidationError]]

## God Nodes (most connected - your core abstractions)
1. `Task` - 68 edges
2. `Workflow` - 65 edges
3. `assert_error()` - 65 edges
4. `TaskService` - 64 edges
5. `TaskRepositoryInterface` - 51 edges
6. `RecordingBus` - 40 edges
7. `State` - 37 edges
8. `create_task()` - 31 edges
9. `TaskSortField` - 29 edges
10. `ErrorCode` - 27 edges

## Surprising Connections (you probably didn't know these)
- `Settings` --implements--> `Per-Environment APP_ENV Configuration`  [EXTRACTED]
  app/core/config.py → docs/FRD.md
- `Task` --implements--> `UTC-Everywhere Timezone Policy`  [EXTRACTED]
  app/services/tasks/domain/models.py → docs/FRD.md
- `TaskService` --references--> `Single-Fetch Tuple Contract (replace/patch)`  [EXTRACTED]
  app/services/tasks/application/service.py → docs/TIS.md
- `EventBus` --implements--> `Post-Commit Domain Event System`  [EXTRACTED]
  app/core/event_bus.py → docs/FRD.md
- `register_exception_handlers()` --implements--> `Standardized Error Envelope`  [EXTRACTED]
  app/core/errors.py → docs/FRD.md

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Domain events published through the EventBus with BackgroundTasks fan-out** — app_core_event_bus_eventbus, app_services_tasks_domain_events_taskcreated, app_services_tasks_domain_events_taskupdated, app_services_tasks_domain_events_taskstatuschanged, app_services_tasks_domain_events_taskcompleted, app_services_tasks_domain_events_taskdeleted, app_services_workflows_domain_events_workflowupdated, app_services_tasks_infrastructure_listeners_log_event [EXTRACTED 1.00]
- **AppError exception hierarchy converted to the envelope by the global handler** — app_core_errors_apperror, app_core_errors_conflicterror, app_core_errors_notfounderror, app_core_errors_validationerror, app_core_errors_readonlyfielderror, app_services_tasks_errors_duplicatetaskerror, app_services_tasks_errors_tasknotfounderror, app_services_tasks_errors_emptyupdateerror, app_services_tasks_errors_invalidtransitionerror, app_services_workflows_errors_workflowvalidationerror, app_services_workflows_errors_workflowstatesinuseerror, app_core_errors_register_exception_handlers [EXTRACTED 1.00]
- **Lifespan startup wiring sequence (logging, schema, bus, listeners)** — app_main_lifespan, app_main_create_app, app_core_logging_setup_logging, app_core_database_init_schema, app_core_event_bus_eventbus [EXTRACTED 1.00]
- **Workflow Definition Update Pipeline (validate -> strand guard -> append version)** — app_services_workflows_module_workflow_service, app_services_workflows_module_collect_all_errors, app_services_workflows_module_strand_guard, app_services_workflows_module_append_only_versioning, docs_frd_workflow_updated [INFERRED 0.90]

## Communities (78 total, 24 thin omitted)

### Community 0 - "Task API Integration Tests"
Cohesion: 0.06
Nodes (81): Response, assert_error(), create_task(), Any, CreateTask, Factory: ``await create_task(title, priority=3)`` → new task id., Assert the standard error envelope; return the parsed ``error`` block., AsyncClient (+73 more)

### Community 1 - "Task Service & Unit Tests"
Cohesion: 0.12
Nodes (33): ValidationError, TaskService, TaskCompleted, TaskCreated, TaskDeleted, TaskStatusChanged, TaskUpdated, InvalidTransitionError (+25 more)

### Community 2 - "App Wiring & Error Envelope"
Cohesion: 0.05
Nodes (52): APIRoute, get_event_bus(), Request, FastAPI, register_exception_handlers(), Event, EventBus, BackgroundTasks (+44 more)

### Community 3 - "Workflow Service Layer"
Cohesion: 0.08
Nodes (26): Any, BackgroundTasks, EventBus, Validate, strand-check, and store a new definition version.          The usage-c, WorkflowService, get_workflow_service(), EventBusDep, SessionDep (+18 more)

### Community 4 - "Error Taxonomy"
Cohesion: 0.10
Nodes (35): ConflictError, _envelope(), _envelope_from_app_error(), ErrorCode, NotFoundError, Error code enum, ``AppError`` hierarchy, and global exception handlers., ReadOnlyFieldError, _envelope_example() (+27 more)

### Community 5 - "Workflow Definition Domain"
Cohesion: 0.10
Nodes (26): _any_to_any(), Seed-equivalent: three states, all entries, every directed pair legal., Single entry, one forward path: new -> in_progress -> completed., _strict(), TransitionTable, States with no path from any entry state (dead columns)., One workflow definition can serve many consumers.      Deliberately not a datacl, The states in column order, as a read-only snapshot. (+18 more)

### Community 6 - "Config & Health"
Cohesion: 0.10
Nodes (21): Effective numeric log level; explicit ``LOG_LEVEL`` overrides the env default., Settings, Environment, OrderDirection, liveness(), JSONResponse, SessionDep, readiness() (+13 more)

### Community 7 - "Task API Router & DTOs"
Cohesion: 0.16
Nodes (24): create_task(), delete_task(), get_task(), list_tasks(), patch_task(), BackgroundTasks, replace_task(), task_transitions() (+16 more)

### Community 8 - "Task Repository Contract"
Cohesion: 0.12
Nodes (22): DuplicateTaskError, ``replace`` and ``patch`` return ``(snapshot_before, row_after)`` from one fetch, TaskRepositoryInterface, ABC-as-Port over Protocol, FixtureRequest, PUT-replace with the same title_key on the same row must not 409 against itself., repo(), test_add_then_get_round_trip() (+14 more)

### Community 9 - "Workflow Repository & Storage"
Cohesion: 0.17
Nodes (16): AppError, Any, Session, Persistence row — unlike ``Task``, the domain entity here is the parsed     ``Wo, SQLModelWorkflowRepository, WorkflowRecord, Append-only storage: the active definition is the highest version., WorkflowRepositoryInterface (+8 more)

### Community 10 - "Task Write Path & Enforcement"
Cohesion: 0.17
Nodes (9): Any, Workflow, Same-state writes are no-moves; anything else needs a defined transition., A status that is no state at all is a validation error, not a refusal., ``workflow`` is None only when the write could not have changed status., The task plus the definition-legal transitions out of its state., BackgroundTasks, Task (+1 more)

### Community 11 - "Task Model & Title Rules"
Cohesion: 0.14
Nodes (11): MUTABLE_FIELDS, Any, Return ``(stripped_title, title_key)``; raise ``ValueError`` if empty., Overwrite every mutable field; ``title_key`` is recomputed from ``title``., Apply a partial update; raise ``ValueError`` for any non-mutable key., Task, Any, TestNormalizeTitle (+3 more)

### Community 12 - "Workflow API & Timestamps"
Cohesion: 0.18
Nodes (14): ensure_utc(), iso_z(), datetime, RFC 3339 in UTC with the ``Z`` suffix — the wire format for timestamps., Return ``dt`` as tz-aware UTC; naive values are treated as already-UTC., get_workflow(), Any, BackgroundTasks (+6 more)

### Community 13 - "Task Repository (SQLModel)"
Cohesion: 0.15
Nodes (10): get_task_service(), EventBusDep, SessionDep, Any, Session, Commit; translate a ``title_key`` UNIQUE violation into ``DuplicateTaskError``., SQLModelTaskRepository, Annotated-Style Dependency Injection (+2 more)

### Community 14 - "Task Listing & Filter Tests"
Cohesion: 0.24
Nodes (17): AsyncClient, Free-form states: an unknown filter value matches nothing (200 []), it is not a, Seeded priorities are 5,3,2,1 — offset=1, limit=2 desc must return the middle wi, SQLite binds offset as INT64 — an unbounded int overflows the driver, not valida, _seed(), test_list_default_sort_is_priority_desc(), test_list_empty_returns_zero_total(), test_list_filter_by_status_multivalue() (+9 more)

### Community 15 - "Project Docs & Core Concepts"
Cohesion: 0.18
Nodes (17): init_schema(), Tasks Module Index (MODULE.md), CLAUDE.md Project Instructions, Functional Requirements Document (FRD), Per-Environment APP_ENV Configuration, Standardized Error Envelope, Hybrid Test Layout Split Rule, Title Uniqueness via title_key (+9 more)

### Community 16 - "Task Model Mutation Tests"
Cohesion: 0.21
Nodes (4): _new(), TestApplyPatch, TestApplyReplace, TestSnapshot

### Community 17 - "Workflow Serialization"
Cohesion: 0.21
Nodes (16): _extract_meta(), _parse_state(), _parse_states(), _parse_transitions(), Any, TransitionTable, Document (de)serialization for workflow definitions.  Kept out of the domain on, The open content model: every key that is not a core field is meta. (+8 more)

### Community 18 - "Workflow Endpoint Tests & Seed"
Cohesion: 0.22
Nodes (15): default_workflow(), Workflow, The behavior-identical default: three states, any → any.      Every state is ``i, _definition_with_review(), Any, AsyncClient, CreateTask, The seeded three states plus a reachable ``review`` column. (+7 more)

### Community 19 - "Request-ID Middleware Tests"
Cohesion: 0.21
Nodes (13): Any, AsyncClient, MonkeyPatch, Replaces ``structlog.BoundLogger`` for tests — captures calls and bound contextv, Each request must emit exactly one ``http_request`` access log with method/path/, 4xx responses produced by exception handlers must still log via the same access, _RecordingLogger, test_middleware_emits_one_http_request_log_per_request() (+5 more)

### Community 20 - "Workflow Domain Modules"
Cohesion: 0.19
Nodes (8): The workflow definition: which states exist and which named moves are legal.  St, _freeze_meta(), Any, Domain model: the value objects a workflow definition is made of., Raise ``ValueError`` unless ``value`` has visible content. The single     home o, Shared ``__post_init__`` tail: guard reserved collisions, wrap meta read-only., require_nonblank(), First-boot seed: store the default definition when the table is empty.

### Community 21 - "Task Sorting & Interfaces"
Cohesion: 0.22
Nodes (6): ABC, Contract knobs for the tasks feature — closed string sets and field bounds., TaskSortField, OrderDirection, OrderDirection, OrderDirection

### Community 22 - "State & Transition Value Objects"
Cohesion: 0.22
Nodes (11): The transition table as a live, read-only view., A named, directed edge between two states (Jira's "Start Progress").      ``meta, Transition, Value objects: construction rules, immutability, hashability., test_meta_keys_cannot_shadow_core_fields(), test_meta_mapping_is_read_only(), test_state_requires_a_name_and_guards_meta(), test_transition_is_immutable() (+3 more)

### Community 23 - "Database & Sessions"
Cohesion: 0.24
Nodes (9): Session, session_factory(), get_session(), Session, SQLModel, SQLite-specific repository tests not covered by the parametrised contract suite., Tiebreaker contract: equal priorities resolve by ``created_at`` ascending (FRD §, session() (+1 more)

### Community 24 - "Task Construction Tests"
Cohesion: 0.20
Nodes (5): Self, Build a Task from caller input, applying normalisation invariants., Detached, revalidated copy for event payloads., TestCreatedAt, TestFromInput

### Community 25 - "Workflow Query API"
Cohesion: 0.18
Nodes (5): Any, Full transitions leaving a state — what a UI renders as buttons., The named state (with its ``meta``) — the single existence check., Raise ``ValueError`` unless ``name`` is a state of this workflow., Define a named legal move. Keyword-only direction: two positional         state

### Community 26 - "Workflow Design Concepts"
Cohesion: 0.20
Nodes (11): Append-Only Versioned Storage, Collect-All-Errors Document Boundary, completes-meta Flag (COMPLETES_META_KEY), WorkflowEngine Not Ported, State/Transition Value Objects (open meta model), Strand Guard, Workflow Definition (states + transitions + reachability), WorkflowRepositoryInterface ABC (+3 more)

### Community 27 - "Pre-commit Hooks"
Cohesion: 0.40
Nodes (5): bandit security hook, file-hygiene hooks, pre-commit hook configuration, ruff + ruff-format hooks, uv-lock-check local hook

### Community 28 - "Hurl E2E & CI"
Cohesion: 0.67
Nodes (3): CI Pipeline, Hurl E2E Suite, Hurl --jobs 1 Constraint

## Knowledge Gaps
- **24 isolated node(s):** `Phase 1 polish plan (Annotated + async)`, `uv`, `task-service compose service`, `Python Assignment Brief`, `Task Entity Requirement (6 properties)` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **24 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Task` connect `Task Model & Title Rules` to `Task Service & Unit Tests`, `Task API Router & DTOs`, `Task Repository Contract`, `Task Repository (SQLModel)`, `Project Docs & Core Concepts`, `Task Model Mutation Tests`, `Task Sorting & Interfaces`, `Database & Sessions`, `Task Construction Tests`?**
  _High betweenness centrality (0.140) - this node is a cross-community bridge._
- **Why does `Workflow` connect `Workflow Definition Domain` to `Task Service & Unit Tests`, `Workflow Service Layer`, `Error Taxonomy`, `Workflow Repository & Storage`, `Workflow Serialization`, `Workflow Domain Modules`, `State & Transition Value Objects`, `Workflow Query API`?**
  _High betweenness centrality (0.111) - this node is a cross-community bridge._
- **Why does `TaskService` connect `Task Service & Unit Tests` to `App Wiring & Error Envelope`, `Error Taxonomy`, `Task API Router & DTOs`, `Workflow Repository & Storage`, `Task Write Path & Enforcement`, `Task Model & Title Rules`, `Task Repository (SQLModel)`, `Project Docs & Core Concepts`, `Workflow Domain Modules`, `State & Transition Value Objects`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Are the 22 inferred relationships involving `Task` (e.g. with `TaskCompleted` and `TaskCreated`) actually correct?**
  _`Task` has 22 INFERRED edges - model-reasoned connections that need verification._
- **Are the 18 inferred relationships involving `Workflow` (e.g. with `FakeRepo` and `FakeWorkflowRepo`) actually correct?**
  _`Workflow` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 9 inferred relationships involving `TaskService` (e.g. with `Transition` and `FakeRepo`) actually correct?**
  _`TaskService` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `TaskRepositoryInterface` (e.g. with `SQLModelTaskRepository` and `TaskSortField`) actually correct?**
  _`TaskRepositoryInterface` has 17 INFERRED edges - model-reasoned connections that need verification._
