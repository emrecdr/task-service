> **Disposition 2026-07-28 (user-decided, main-thread approvals):** ALL candidates below are DEFERRED — including ADR-001/ADR-002/CON-001/FLOW-001, which were initially approved and then deferred by explicit user instruction. REJ-001 (cosmic-python-ceremony) was SKIPPED entirely (user declined recording a tombstone). Nothing was written to permanent memory; proposed IDs are not reserved. Re-run `/devt:memory promote` to revisit.

# Memory Layer — Discovery Suggestions

Generated: 2026-07-27T23:12:02.883Z

**This report is auto-generated. NO permanent files are written without explicit user approval via curator's AskUserQuestion flow.**

---

## Summary
- total_candidates: 22
- promoted_to_review: 22
- suppressed_by_rej: 0
- filtered_as_duplicates: 0
- wiki_links_to_add: 0

## ⚖️/🔵 Proposed Promotions

Each proposal carries the FULL original reasoning verbatim. Curator presents these via AskUserQuestion.

### ⚖️ SQLModel Task row IS the domain entity; domain events carry domain Task snapshots, never application DTOs — FRD §5.1's "task: TaskResponse" payload wording is outdated docs, not a code bug (fixing code to match would invert domain→application layering).
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 Error-envelope invariant: every non-2xx must flow through the central handlers in app/core/errors.py; FRD §4 row 165 mandates a catch-all Exception→500 internal_error handler as part of this invariant (implemented: catch-all at app/core/errors.py:141-151 closed the hole on 2026-07-27).
- Source: scratchpad
- Proposed type: concept

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 PATCH boundary must distinguish field-omitted from explicit-null on non-nullable fields; model_dump(exclude_unset=True) alone cannot — explicit JSON null passes through and the DTO must reject it (TaskPatch title/status/priority).
- Source: scratchpad
- Proposed type: concept

**Original reasoning (verbatim):**
```
(no body)
```

### ⚖️ Event base class co-lives with EventBus in app/core/event_bus.py, which imports fastapi.BackgroundTasks — domain events therefore carry a transitive fastapi dependency. Accepted for Phase 1 under the documented BackgroundTasks exception; split Event out of event_bus.py only when the broker changes in Phase 2.
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 DB-error translation flow: repository._commit_or_translate translates only the title_key UNIQUE violation into DuplicateTaskError (rollback + re-raise everything else); all other driver errors depend on the global catch-all for enveloping.
- Source: scratchpad
- Proposed type: flow

**Original reasoning (verbatim):**
```
(no body)
```

### REJ Cosmic-Python ceremony (separate ports/, Protocol typing, domain/ORM entity split, import-linter) deliberately rejected for Phase 1 — documented in CLAUDE.md but absent from .devt/memory/rejected/; promotion candidate so future scans stop re-proposing it.
- Source: scratchpad
- Proposed type: rejected

**Original reasoning (verbatim):**
```
(no body)
```

### ⚖️ Cross-feature seam = owning-repository injection: a service receives the sibling feature's repository ABC via constructor (TaskService gets WorkflowRepositoryInterface, WorkflowService gets TaskRepositoryInterface); only dependencies.py may import the sibling's CONCRETE repository, and both repos are built from the same request session — the single-session invariant that makes read-check-write spans atomic under single-threaded loop + StaticPool. Phase 2 (Postgres/multi-worker) must replace await-free-span atomicity with transactional guards.
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 Completes-meta contract: workflow machinery never interprets state meta; the tasks feature reads exactly one key — "completes" (COMPLETES_META_KEY, app/services/tasks/constants.py:22) — to fire TaskCompleted on state entry. The spelling also appears raw in workflows/infrastructure/seed.py:25 and in stored definition documents: it is persisted wire vocabulary, currently not single-sourced.
- Source: scratchpad
- Proposed type: concept

**Original reasoning (verbatim):**
```
(no body)
```

### ⚖️ Workflow definitions are append-only versioned rows: every PUT /v1/workflow inserts version=max+1 (workflows/infrastructure/repository.py:43-47); the active definition is the highest version; rollback = re-PUT an older document; no UPDATE path exists anywhere.
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 Status-enforcement flow: TaskService.create/replace/patch → workflows.get_active() fresh per request (no cache, deliberate) → unknown state = 422 validation_error / non-entry create or undefined (from,to) = 409 invalid_transition (same-state writes are no-moves) → repo write → events. Tasks is the enforcement point; workflows only defines legality.
- Source: scratchpad
- Proposed type: flow

**Original reasoning (verbatim):**
```
(no body)
```

### ⚖️ Workflows persistence splits domain from row (parsed Workflow vs WorkflowRecord document store) — deliberate divergence from tasks' row-as-entity, correct for versioned JSON documents; do not "unify" the two patterns.
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### ⚖️ PUT /v1/workflow rejects server-owned version/created_at as unknown-top-level-key 422 invalid_workflow_definition (serialization.py:82-85), NOT read_only_field — the body is a document, not the resource; deliberate asymmetry with tasks endpoints, pin with one FRD sentence.
- Source: scratchpad
- Proposed type: decision

**Original reasoning (verbatim):**
```
(no body)
```

### 🔵 Workflow — 73 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `Workflow` as a god-node with 73 edges. High-fanin concepts are typical CON-* candidates: define what `Workflow` is, who depends on it, and the invariants callers rely on.
```

### 🔵 Task — 69 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `Task` as a god-node with 69 edges. High-fanin concepts are typical CON-* candidates: define what `Task` is, who depends on it, and the invariants callers rely on.
```

### 🔵 TaskService — 62 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `TaskService` as a god-node with 62 edges. High-fanin concepts are typical CON-* candidates: define what `TaskService` is, who depends on it, and the invariants callers rely on.
```

### 🔵 TaskRepositoryInterface — 52 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `TaskRepositoryInterface` as a god-node with 52 edges. High-fanin concepts are typical CON-* candidates: define what `TaskRepositoryInterface` is, who depends on it, and the invariants callers rely on.
```

### 🔵 State — 37 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `State` as a god-node with 37 edges. High-fanin concepts are typical CON-* candidates: define what `State` is, who depends on it, and the invariants callers rely on.
```

### 🔵 ValidationError — 29 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `ValidationError` as a god-node with 29 edges. High-fanin concepts are typical CON-* candidates: define what `ValidationError` is, who depends on it, and the invariants callers rely on.
```

### 🔵 TaskSortField — 28 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `TaskSortField` as a god-node with 28 edges. High-fanin concepts are typical CON-* candidates: define what `TaskSortField` is, who depends on it, and the invariants callers rely on.
```

### 🔵 ErrorCode — 26 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `ErrorCode` as a god-node with 26 edges. High-fanin concepts are typical CON-* candidates: define what `ErrorCode` is, who depends on it, and the invariants callers rely on.
```

### 🔵 workflow_from_document — 25 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `workflow_from_document` as a god-node with 25 edges. High-fanin concepts are typical CON-* candidates: define what `workflow_from_document` is, who depends on it, and the invariants callers rely on.
```

### 🔵 TaskUpdated — 23 edges (graphify god-node)
- Source: graphify-god-node
- Proposed type: concept

**Original reasoning (verbatim):**
```
Graphify identified `TaskUpdated` as a god-node with 23 edges. High-fanin concepts are typical CON-* candidates: define what `TaskUpdated` is, who depends on it, and the invariants callers rely on.
```
