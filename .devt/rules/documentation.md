# Documentation — Python / FastAPI

## MODULE.md (Required per Service)

Every service module must maintain a `MODULE.md` at its root directory. Use
[`module-template.md`](./module-template.md) as the scaffold when creating a new service —
it encodes the canonical section order, base-class conventions, and `AppError` HTTP-status
mapping expected by every greenfield service.

### Location

```
app/services/<service_name>/MODULE.md
```

### Required Sections

1. **Overview** — What this module does, its domain boundaries
2. **Models** — Domain entities, their fields, and relationships
3. **Capabilities** — Business operations the service provides
4. **Endpoints** — API routes with methods, paths, and descriptions
5. **Dependencies** — Other modules this service depends on
6. **Tests** — Test coverage summary and notable test scenarios

### When to Update

- Adding or modifying domain models
- Adding or changing service capabilities
- Adding or modifying API endpoints
- Changing module dependencies
- Adding database migrations
- Refactoring domain boundaries

## Code Documentation

- Docstrings on all public functions and classes
- Type hints serve as primary documentation for signatures
- Complex business rules get inline comments explaining WHY, not WHAT
- No TODO comments — all code must be complete and functional

## API Documentation

- FastAPI auto-generates OpenAPI docs from route decorators
- Use `summary` and `description` on route decorators
- Use `response_model` for typed responses
- Document error responses with `responses` dict on endpoints
- Pydantic model `Field(description=...)` for request/response field docs

## Project-Level Documentation

- `docs/architecture/` — System design, standards, principles
- `docs/guides/` — How-to guides for common tasks
- `docs/ops/` — Operational docs (CI/CD, env vars, deployment)
- Service-specific docs stay WITH the service, not in `docs/`

## Naming Convention

- All documentation files use UPPERCASE-WITH-HYPHENS: `MODULE.md`, `API-DESIGN.md`
- Exception: ADR files use kebab-case

---

## Before Implementation: Read MODULE.md (MANDATORY)

**YOU MUST read MODULE.md files BEFORE implementation.** Failure leads to:
- Duplicate systems (creating a Logger when obslog exists)
- Models in wrong service (UserMeta in licences instead of identity)
- Circular dependencies (services depending on each other incorrectly)

### Which Files to Read

1. **Always read:** `app/core/MODULE.md` — Shared services and capabilities
2. **Target service:** `app/services/<target-service>/MODULE.md`
3. **Dependencies:** `app/services/<dependency-service>/MODULE.md`

### What to Look For

| Check | Question |
|-------|----------|
| **Models** | Does the model I need already exist? Is it in the correct service? |
| **Capabilities** | Does similar functionality already exist? |
| **External Services** | Is this API already integrated? What pattern is used? |
| **Architecture** | Are there circular dependency risks? |

### Model Ownership

Each domain model belongs to exactly one service. Check ownership before placing models:

| Model Category | Correct Service | Wrong Service |
|----------------|-----------------|---------------|
| User, Session, Role | Identity | Any other |
| License, SKU | Licences | Identity |
| Client, Relationship | Clients | Identity |
| Organization | Organizations | Clients |

### Dependency Rules

```
core (no dependencies)
  ^
identity (depends on core)
  ^
  +-- clients (depends on identity + core)
  +-- licences (depends on identity + core)
  +-- organizations (depends on identity + core)
```

Services CANNOT depend on each other except via identity (or core).

---

## MODULE.md Update Triggers

Update MODULE.md after ANY of these changes:

| Change | Section to Update |
|--------|------------------|
| Added new model | Models |
| Added new endpoint | Capabilities |
| Integrated external API | External Services |
| Added repository method | Repository Interfaces |
| Added dependency | Dependencies |
| Architectural decision | Notes |
| Moved model between services | Models (both source and target) |
| Added database migration | Notes |
| Changed cross-service interfaces | Dependencies, Repository Interfaces |
| Refactored domain boundaries | All relevant sections |

### When NOT to Update MODULE.md

Do NOT update for:
- Ruff/mypy/linting fixes (no functional change)
- Test-only changes that don't add new test scenarios
- Internal variable renames (no API change)
- Comment changes
- Dependency version bumps (unless API changes)

---

## Model Documentation Template

Document ALL database models in each service's MODULE.md:

```markdown
## Models

- **<ModelName>** (table=True)
  - Table: <table_name>
  - Purpose: <what this model stores>
  - Key fields: <important fields and their types>
  - Relationships: <foreign keys and relationships>
  - Constraints: <unique constraints, indexes>
```

**Example:**

```markdown
## Models

- **User** (table=True)
  - Table: users
  - Purpose: User account storage
  - Key fields: id (UUID), email (VARCHAR, unique), hashed_password (VARCHAR)
  - Relationships: sessions (one-to-many), user_roles (one-to-many)

- **Session** (table=True)
  - Table: sessions
  - Purpose: User session tracking for authentication
  - Key fields: id (UUID), user_id (FK->users), token (VARCHAR), expires_at (DATETIME)
  - Relationships: user (many-to-one)
```

## External Service Integration Template

```markdown
## External Services

- **<ServiceName>:** <Purpose>
  - Integration: <Pattern used (factory, singleton, etc.)>
  - Location: <File path>
  - Usage: <How it's used in this service>
  - Configuration: <Required env vars>
```

**Example:**

```markdown
- **SendGrid:** Email verification, password reset
  - Integration: Factory pattern via EmailClientFactory (app/core/external/email/)
  - Usage: Email sending via dependency injection
  - Configuration: SENDGRID_API_KEY_SECRET, EMAIL_FROM_ADDRESS
```

## Repository Interface Documentation

```markdown
## Repository Interfaces

- **<RepositoryName>:** <Purpose>
  - Methods: <list of key methods>
  - Filters: <EntityFilters model fields>
```

## Complete MODULE.md Structure

Every service module MUST have these sections:

1. **Responsibility** — What this service does (one paragraph)
2. **Models** — Database tables with purpose, fields, relationships
3. **Capabilities** — Operations this service provides
4. **Endpoints** — API routes with methods, paths, descriptions
5. **External Services** — Third-party API integrations
6. **Repository Interfaces** — Available repository methods
7. **Dependencies** — Internal and external dependencies
8. **Notes** — Known issues, technical debt, architectural decisions

### Validation Checklist

Before marking MODULE.md update complete:

- [ ] All new models documented with purpose, fields, relationships
- [ ] New capabilities added
- [ ] External services documented with integration pattern
- [ ] Repository interfaces listed
- [ ] Dependencies updated (internal and external)
- [ ] Notes explain architectural decisions
- [ ] No TODOs or placeholders
- [ ] Formatting consistent with other MODULE.md files
