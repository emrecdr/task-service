---
type: "query"
date: "2026-05-14T18:07:09.431576+00:00"
question: "Why does Task bridge Event Bus and Service Core, Task Model Unit Tests, Health and Database, and SQLModel Repository"
contributor: "graphify"
source_nodes: ["Task", "Status", "TaskService", "SQLModelTaskRepository", "init_schema"]
---

# Q: Why does Task bridge Event Bus and Service Core, Task Model Unit Tests, Health and Database, and SQLModel Repository

## Answer

Task is the single class spanning domain invariants (normalize_title, title_key, UTC created_at), ORM persistence (SQLModel table=True row), test surface (TestNormalizeTitle, TestFromInput, TestCreatedAt reach in directly), and bootstrap (init_schema registers its table). Its high betweenness (0.070) is intentional: CLAUDE.md states 'the Task SQLModel row IS the domain entity (table=True). There is no separate ORM/domain split in Phase 1.' This is the documented Phase 1 trade-off. Task is the highest-leverage refactor point — splitting domain entity from ORM row in a Phase 2 would fission this single node into two. Status enum shows the same pattern at smaller scale: degree 23 from being the 4-value spine across enums, DTOs, repo filters, events, and tests. Also surfaced: the graph has two TaskService nodes (application_service_taskservice vs service_taskservice) from AST and semantic extractors using different ID prefixes — a graphify normalization bug, not a code bug.

## Source Nodes

- Task
- Status
- TaskService
- SQLModelTaskRepository
- init_schema
