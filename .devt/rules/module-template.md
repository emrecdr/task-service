<!-- TEMPLATE COMPLETION CHECKLIST (delete this block once filled):
Before submitting this MODULE.md file, verify:
- [ ] [Module Name] replaced with actual service/module name
- [ ] Responsibility section is 2-3 meaningful sentences (no placeholders)
- [ ] Every model lists its Base Class (one of BaseUUIDEntityWithSD / BaseUUIDEntity / BaseIntEntityWithSD / BaseIntEntity)
- [ ] Every model lists Table, Purpose, Key fields with types, Relationships, Constraints
- [ ] Capabilities list real business features (not placeholder text)
- [ ] Exceptions table maps each error class to its `AppError` subclass + HTTP status
- [ ] Repository Interfaces section names the contract (`SoftDeleteRepositoryContract` or `RepositoryContract`) and lists domain-specific methods
- [ ] Dependencies list is split between Internal (other services / `app.core.*`) and External (PyPI packages)
- [ ] API Endpoints section reflects actual routes (or section is deleted if module exposes no HTTP API)
- [ ] Optional sections marked "(if applicable)" are filled in OR deleted
- [ ] No TODOs, no temporal markers (NEW/UPDATED/FIXED), no version suffixes (_v2, _new)
- [ ] Cross-references to other MODULE.md files use relative links
- [ ] Remove this checklist block after completing all items
-->

# Module: [Module Name]

<!--
DOCUMENTATION SEPARATION GUIDE:
- MODULE.md (this file): Technical reference for developers and AI agents
  → Models, repositories, dependencies, architecture, API specs
- README.md (optional): Business rules for product owners, QA, stakeholders
  → Permission matrices, workflows, validation rules, business scenarios

If this service has complex business rules, create a README.md with cross-reference:
> **Business Rules**: See [README.md](./README.md) for user-facing business rules and permissions.
-->

> **Business Rules**: See [README.md](./README.md) for user-facing business rules and permissions. *(delete this line if no README.md)*

## Responsibility

<!-- 2-3 sentences explaining WHAT this module does and WHY it exists.
     Name the business domain in plain language. -->

[Brief description of the business domain this module owns and the capabilities it provides.]

## Architecture (if applicable)

<!-- Use this section ONLY if the module has a non-obvious architectural pattern
     that needs explaining (resource ownership, event flows, multi-container storage, etc.).
     Otherwise delete the section. -->

[Diagram or prose describing the module's architectural shape. Include any
ownership rules, lifecycle invariants, or cross-domain interactions specific
to this module.]

## Models

<!-- List all SQLModel entities. Every entity MUST extend a base class from
     app/core/domain/base_entity.py. -->

### [EntityName1]

**Table:** `table_name`
**Base Class:** `BaseUUIDEntityWithSD` *(or BaseUUIDEntity / BaseIntEntityWithSD / BaseIntEntity)*
**Purpose:** [What this entity represents and why it exists]
**Key fields:**
- id (UUID, PK, inherited)
- [field_name] ([type], [constraint — e.g., FK to table.id, indexed, nullable])
- created_at, updated_at, deleted_at (inherited if WithSD)
**Relationships:** [related_entity] (one-to-many → [RelatedEntity])
**Constraints:** [unique indexes, partial indexes, check constraints]

### [EntityName2]

**Table:** `table_name`
**Base Class:** [base class]
**Purpose:** [...]
**Key fields:** [...]
**Relationships:** [...]
**Constraints:** [...]

### [EnumName] (Enum)

**Values:** [VALUE1, VALUE2, VALUE3]
**Purpose:** [What this enum represents and where it is used]

## Constants (if applicable)

<!-- Document module-level constants from constants.py.
     Delete this section if the module has no public constants. -->

**File:** `constants.py`

| Constant | Type | Purpose |
|----------|------|---------|
| `MODULE_NAME` | str | `"[ServiceName]"` — identifier used in logging/observability |
| `[CONSTANT_NAME]` | [type] | [purpose] |

### Helper Functions (if any)

- `[function_name](args) -> ReturnType`: [what it does]

## Exceptions

<!-- All exceptions MUST inherit from AppError or one of its subclasses
     (NotFoundError, BadRequestError, ForbiddenError, ConflictError, etc.).
     Never inherit from plain Exception. -->

**File:** `errors.py`

| Exception | Base Class | HTTP Status | Purpose |
|-----------|------------|-------------|---------|
| `[ServiceName]ServiceError` | `AppError` | 500 | Base exception for all module errors |
| `[Resource]NotFoundError` | `NotFoundError` | 404 | [Resource] not found by ID |
| `[Resource]ValidationError` | `BadRequestError` | 400 | Invalid input for [resource] |
| `[Resource]PermissionError` | `ForbiddenError` | 403 | [Resource] access denied |
| `[Resource]ConflictError` | `ConflictError` | 409 | [Resource] conflict (e.g., duplicate name) |

### Repository Error Handling

All repository write operations use `db_error_handler` from `app/core/db_utils.py` for consistent
database error translation, session rollback, and structured logging.

**Custom Error Overrides (if any):**
- `[Entity].add()`: `on_unique=[CustomError]` — [when this overrides the default ConflictError]

For default error mappings, see [`app/core/MODULE.md`](../../core/MODULE.md).

## Domain Events (if applicable)

<!-- Document events published via the event bus (app.core.event_bus).
     Delete this section if the module does not publish events. -->

**File:** `domain/events.py`

| Event | Audit Action | Fields |
|-------|--------------|--------|
| `[Resource]CreatedEvent` | `[resource]_created` | [resource]_id, actor_id, [other fields] |
| `[Resource]UpdatedEvent` | `[resource]_updated` | [resource]_id, actor_id, [changed fields] |
| `[Resource]DeletedEvent` | `[resource]_deleted` | [resource]_id, actor_id |

### Audit Trail Integration

Mutating operations emit domain events consumed by the audit service via the event bus. The audit
mapper transforms these events into `audit_logs` records with automatic `actor_name` / `actor_email`
enrichment from `event.metadata`.

See [Adding Audit Events Guide](../../../../docs/guides/ADDING-AUDIT-EVENTS.md) for the full flow.

## Capabilities

<!-- MANAGED:START - docs-writer updates this section -->
<!-- Business features — what users/systems can do with this module.
     Use sub-headings (### Feature Name) when a capability has substantial detail. -->

### [Capability 1: e.g., User registration]
[1-3 sentences describing the feature, including any non-obvious behaviour
(self-healing, rate limits, idempotency, etc.).]

### [Capability 2: e.g., Password reset]
[Description]

### [Capability 3]
[Description]

<!-- MANAGED:END -->

## External Services (if applicable)

<!-- Third-party integrations: SendGrid, Pushy, Stripe, Azure Blob, etc.
     Delete this section if the module has no external integrations. -->

### [ServiceName]

**Pattern:** [Singleton via DI / Factory / Direct instantiation]
**Backend Protocol:** `app.core.external.[backend_name].[BackendProtocol]`
**Usage:** [How and why this external service is used]
**Configuration:** [Required env vars — e.g., `SENDGRID_API_KEY_SECRET`]
**Failure mode:** [Fail-open / fail-closed / retry policy]

## Repository Interfaces

<!-- Data access layer. Every repository MUST extend a contract from
     app/core/domain/repository_contracts.py.
     Use SoftDeleteRepositoryContract for entities with soft delete (WithSD bases).
     Use RepositoryContract for entities without soft delete. -->

### [Entity1]RepositoryInterface

**Extends:** `SoftDeleteRepositoryContract[[Entity1], UUID, [Entity1]Filters]`
**File:** `repository_interfaces.py`

**Inherited Methods:**
- `get_by_id(entity_id: UUID) -> [Entity1] | None`
- `get_by_ids(entity_ids: Iterable[UUID]) -> list[[Entity1]]`
- `exists(entity_id: UUID) -> bool`
- `count(filters: [Entity1]Filters | None) -> int`
- `list_all(params: QueryParams[[Entity1]Filters]) -> Page[[Entity1]]`
- `add(entity: [Entity1]) -> [Entity1]`
- `add_many(entities: Iterable[[Entity1]]) -> list[[Entity1]]`
- `update(entity: [Entity1]) -> [Entity1]`
- `delete(entity_id: UUID, deleted_by: UUID | None) -> None` *(soft delete)*
- `restore(entity_id: UUID) -> [Entity1] | None`
- `delete_hard(entity_id: UUID) -> None`

**Domain-Specific Methods:**
- `get_by_[domain_field]([param]: [type]) -> [return_type]` — [purpose]
- `[other_method](...)` — [purpose]

**Filters:** `[Entity1]Filters` (Pydantic model in `repository_interfaces.py`)
- `[field_name]: [type] | None = None` — [filter purpose]

**Purpose:** [What data access this repository provides]

### [Entity2]RepositoryInterface (if applicable)

**Extends:** `RepositoryContract[[Entity2], int, [Entity2]Filters]`
**Domain-Specific Methods:** [list]
**Purpose:** [...]

### Cross-Service Repository Usage

<!-- List repositories owned by OTHER services that this module injects.
     Each entry MUST justify why cross-domain access is needed. -->

- **`[OtherService]RepositoryInterface`** (from `app.services.[other_service]`)
  **Used for:** [What this module reads/writes via the other service's repo]
  **Methods used:** `[method_name]`, `[other_method]`

## Application Services

### [Service1Name]

**File:** `application/[service_name].py`
**Purpose:** [Main orchestration responsibility — 1-2 sentences]
**Dependencies (injected):**
- `[Entity1]RepositoryInterface`
- `[Entity2]RepositoryInterface`
- `[ExternalBackendProtocol]` *(if any)*
- `EventBusDep` *(if the service publishes events)*

**Key Methods:**
- `[method_name](args) -> ReturnType` — [purpose]
- `[method_name](args) -> ReturnType` — [purpose]

### [Service2Name] (if applicable)

**File:** `application/[service_name].py`
**Purpose:** [...]

## API Endpoints

<!-- List FastAPI routes. Group by router file when there are many.
     Every endpoint MUST have a corresponding test (Rule 9: API/Test Alignment). -->

### [Resource] API
**Base Path:** `/api/v1/[base_path]`
**File:** `api/v1/[router_file].py`

| Method | Path | Purpose | Auth | Permissions |
|--------|------|---------|------|-------------|
| GET | `/` | List [resources] | JWT | `[SCOPE]:READ` |
| POST | `/` | Create [resource] | JWT | `[SCOPE]:CREATE` |
| GET | `/{id}` | Get [resource] by ID | JWT | `[SCOPE]:READ` |
| PATCH | `/{id}` | Update [resource] | JWT | `[SCOPE]:UPDATE` |
| DELETE | `/{id}` | Delete [resource] (`?permanent=bool`) | JWT | `[SCOPE]:DELETE` |

**Response Schemas:** [Pydantic response models — e.g., `[Resource]Response`, `[Resource]ListResponse`]
**Error responses:** Documented via `responses={}` on each endpoint, mapped to AppError subclasses
through `app/core/error_handlers.py`.

## Configuration (if applicable)

<!-- Module-level Pydantic BaseSettings. Delete if the module has no settings.py. -->

**File:** `settings.py`
**Class:** `[ModuleName]Settings` (extends `BaseSettings`)

| Variable | Default | Description |
|----------|---------|-------------|
| `[VAR_NAME]` | `[default]` | [purpose] |

## Dependencies

### Internal Dependencies

<!-- Other services and core modules this depends on.
     Format: **module.path:** what is consumed (specific functions/protocols, not vague). -->

- **`app.core.database`:** `get_sync_session` for repository session injection
- **`app.core.observability`:** `obslog` for structured logging
- **`app.core.errors`:** `AppError` and subclasses for HTTP status mapping
- **`app.core.db_utils`:** `db_error_handler` for repository error translation
- **`app.core.event_bus`:** Event publishing *(if applicable)*
- **`app.services.identity`:** `ActiveUser` dependency for JWT auth context
- **`app.services.[other_service]`:** [specific repository interface or capability]

### External Dependencies

<!-- Third-party packages. Pin major versions if this module is sensitive to upgrades. -->

- **fastapi:** Web framework, routing, dependency injection
- **sqlmodel:** ORM with type hints (Session, select)
- **pydantic:** DTO validation and serialization
- **[other-package]:** [purpose]

## Cross-Domain Dependencies (if applicable)

<!-- Diagram of cross-service composition. Use this when the service orchestrates
     multiple domains. Delete if the module is self-contained. -->

```
[ModuleName]Service
├── [Own]Repository (own domain)
├── [Other]RepositoryInterface (from app.services.[other_service])
├── [Backend]Protocol (from app.core.external.[backend])
└── EventBus (from app.core.event_bus)
```

**Key Pattern:** Services orchestrate repositories from multiple domains while each repository
maintains single-table responsibility. Cross-domain queries are FORBIDDEN inside repositories.

## Database Migrations (if applicable)

<!-- List the Alembic migrations that built this module's schema.
     Reference recent / important ones; full history lives in alembic/versions/. -->

| Migration | File | Purpose |
|-----------|------|---------|
| `[revision_id]` | `[filename].py` | [what schema change it introduced] |

## Notes

<!-- MANAGED:START - Agents update this section as issues are discovered/resolved -->

### Implementation Status
- [ ] / ✅ [Major capability area 1]
- [ ] / ✅ [Major capability area 2]

### Architecture Notes

- **[Pattern name]:** [Description of any non-obvious architectural decision]
- **[Constraint]:** [Description of any invariant the module enforces]

### Known Issues

<!-- Technical debt, limitations, temporary workarounds.
     Write "None at this time" if there are no known issues. -->

- [Issue 1: e.g., "Photo upload limited to 10MB pending CDN integration"]

### Migration Context (if applicable)

<!-- Brownfield → Greenfield migration notes, phase information.
     Delete this subsection if the module is greenfield-native. -->

- [Migration note: e.g., "Migrated from brownfield PHP endpoints in Phase 2"]
- **Endpoint mappings:**
  - `legacy/api/old_endpoint.php` → `api/v1/new_endpoint` (POST)

### Performance Considerations (if applicable)

- [Indexed fields, query patterns, denormalization decisions]

### Security Considerations (if applicable)

- [Authorization layers, input sanitization, scope validation]

<!-- MANAGED:END -->

## Test Coverage

<!-- Summarize test coverage. Be specific about what is and isn't covered. -->

**Unit Tests:** `tests/unit/`
- [What is unit tested — DTOs, service helpers, pure functions]

**Integration Tests:** `tests/integration/`
- [What is integration tested — repository CRUD, event handlers]

**HURL Tests:** `tests/hurl/` *(if applicable)*
- [End-to-end HTTP flows covered]

## Related Documentation (if applicable)

<!-- Links to other guides in this directory or repository. -->

- [./README.md](./README.md) — Business rules and permission matrices
- [../../core/MODULE.md](../../core/MODULE.md) — Shared infrastructure (base classes, error handling)
- [./[GUIDE_NAME].md](./[GUIDE_NAME].md) — [Purpose]
