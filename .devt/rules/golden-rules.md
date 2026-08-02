# Golden Rules — Python / FastAPI

> Non-negotiable rules for all development work. Violations require immediate stop and correction.

## Quick Reference Card

| Rule | One-Liner |
|------|-----------|
| 1. Deep Analysis | Scan ALL related code BEFORE implementing |
| 2. No Duplicates | NEVER reimplement existing features OR create method aliases |
| 3. No Backward Compat | Update callers directly — no compatibility shims |
| 4. Surgical Changes | Modify only what task needs; surface unrelated findings instead of silently fixing |
| 5. Read MODULE.md | Check documentation BEFORE implementing |
| 6. Base Entity Classes | Entities extend CORRECT base class (UUID/Int + SD) |
| 7. Scope Validation | Validate user scope in ALL repository methods |
| 8. Service Isolation | Services use repositories, NEVER direct DB access |
| 9. API/Test Alignment | Every `responses={}` code MUST have a test |
| 10. Refactoring Verify | Verify no loss + update ALL affected code/docs |
| 11. No TODOs/Markers | Complete code only — no placeholders or temporal markers |
| 12. Verify Before Done | No completion claims without fresh verification evidence |

---

## Rule 1: Deep Analysis Before Implementation

```
NO IMPLEMENTATION WITHOUT CODEBASE SCAN. NO EXCEPTIONS.
```

**ALWAYS scan ALL related code BEFORE any implementation.**

### Why It Matters

Prevents wasted effort implementing features that already exist, avoids duplicate/conflicting code, ensures accurate completion status, and prevents architectural violations.

### Required Process

Before ANY implementation work:

1. **Scan target service exhaustively:**
   - Read EVERY file in `app/services/<target-service>/`
   - Check `infrastructure/models.py`, `application/service.py`, `api/v1/routes.py`
   - Check `tests/` — reveals actual functionality

2. **Scan core shared services:**
   - Read `app/core/` for shared capabilities
   - Check for duplicate functionality (logging, notifications, email)

3. **Scan related services:**
   - Read any dependency services
   - Search for integration points

4. **Document findings BEFORE proposing work:**
   - List what EXISTS (with file paths)
   - List what is TRULY missing
   - Calculate ACCURATE completion percentage

**Scan scope by service size:**

| Size | Files | Scan approach |
|------|-------|--------------|
| Small (1-10 files) | Read ALL files + tests |
| Medium (10-30 files) | Read MODULE.md + domain/ + application/ + target files + tests |
| Large (30+ files) | Read MODULE.md + Grep for related patterns + Read direct dependencies + tests |

### Violation Example

Implementing a push notification service when `app/core/external/push/` already provides a factory-based push backend.

| Excuse | Reality |
|--------|---------|
| "Too simple to scan" | Simple tasks touch existing code that has patterns to follow |
| "I already know this module" | You know what you last saw. Code changes. Scan. |
| "Only changing one file" | One file imports from many. Scan dependencies. |
| "Under time pressure" | Scanning takes 2 minutes. Rework takes hours. |

### Enforcement

- **Implementer** must present scan findings before implementation
- **Reviewer** must reject PRs without scan evidence

---

## Rule 2: No Duplicate Features or Methods

**NEVER implement a feature that already exists. NEVER create method aliases.**

### Why It Matters

Duplicate code creates maintenance nightmares. Two implementations diverge over time — bugs fixed in one, not the other. Method aliases bloat the API surface and create cognitive overhead.

### Check Before Implementing

```bash
# Search for similar endpoints
grep -r "POST /api/v1/photos" app/services/

# Search for existing models
grep -r "class PhotoAlbum" app/services/

# Search for similar service methods
grep -r "def send_notification" app/services/
```

### No Duplicate Methods

Each operation MUST have exactly ONE method name:

```python
# FORBIDDEN - Duplicate methods (aliases)
class UserRepository:
    def create(self, user: User) -> User: ...
    def add(self, user: User) -> User:  # ALIAS = FORBIDDEN
        return self.create(user)

# CORRECT - One method per operation
class UserRepository:
    def add(self, user: User) -> User: ...     # Single create method
    def get_by_id(self, id: UUID) -> User: ... # Single get method
```

| Duplicate Pair | Keep | Remove |
|----------------|------|--------|
| `create()` / `add()` | `add()` | `create()` |
| `get_by_id()` / `get_by_uuid()` | `get_by_id()` | `get_by_uuid()` |
| `delete()` / `remove()` | `delete()` | `remove()` |
| `update()` / `save()` | `update()` | `save()` |
| `find()` / `get()` / `fetch()` | `get_by_*()` | `find_*()` / `fetch_*()` |

When duplicates are found: choose canonical name, update ALL usages across the codebase, delete the duplicate, run tests.

### Violation Example

Creating a `RoleRepositoryProtocol` in your service when `identity/repository_interfaces.py` already defines `RoleRepositoryInterface`.

### Enforcement

- **Implementer** must search for existing implementations before creating new ones
- **Reviewer** must reject PRs that introduce duplicate methods or protocols

---

## Rule 3: No Backward Compatibility Code

**Prefer direct changes over compatibility layers. Update all callers, delete old paths.**

### Why It Matters

Dead compatibility code creates confusion, false sense of completion, and maintenance burden. The codebase should represent the current state, not carry historical baggage.

### Forbidden Patterns

- "for backward compatibility" comments
- Legacy code traces or migration shims
- Version compatibility matrices
- Deprecated pattern preservation
- Commented-out old implementations

### Correct Approach

- Clean, modern implementation using current patterns
- Latest Python 3.14+ features (stdlib `uuid.uuid7()`, `compression.zstd`, PEP 695 type syntax, `T | None`, `list[int]`)
- FastAPI (lifespan, `Annotated` deps), Pydantic v2 (`ConfigDict`, `field_validator`), SQLModel best practices
- If the project has external API consumers, coordinate breaking changes — but no internal shims

### Violation Example

Keeping both a `V1PhotoResponse` and `V2PhotoResponse` "for clients that haven't migrated yet."

### Enforcement

- **Reviewer** must reject any code with backward-compatibility patterns

---

## Rule 4: Surgical Changes

**Touch only what the task requires. Clean up orphans your own changes create — not pre-existing ones.**

### Why It Matters

LLM agents tend to over-improve adjacent code, conflating "I noticed it" with "I should fix it." Drive-by edits create review noise, conflict with parallel work, and obscure the real change. Every modified line should trace directly to the user's request.

### What This Means

When working on ANY code:
- Modify only what is necessary to complete the task
- Remove imports/symbols/dead branches that **your changes** orphaned — they are your mess
- Match existing project conventions even if you would write it differently
- Do NOT silently fix unrelated issues you happen to notice

### Find-Surface-Decide Protocol

When you spot unrelated improvements or bugs (typos, dead code, stale comments, missing type hints, latent bugs, refactor opportunities, security smells):

1. **Find**: note the file path and a one-line description of the issue
2. **Surface**: present it to the user as a side-finding, not a fait accompli
3. **Decide**: ask whether to (a) fix now in this task, (b) split into a follow-up task, or (c) just record in the session summary
4. Act on the user's choice — never assume

### Boy Scout Mode (opt-in)

`scope_mode` in `.devt/config.json` defaults to `"surgical"` (Find-Surface-Decide above). Set it to `"boyscout"` to grant agents permission to auto-fix small mechanical issues — unused imports, ruff/black warnings, missing type hints on touched signatures, typos in docstrings, formatting — within files they are already editing, without asking. Anything larger (refactors, behavior changes, cross-module cleanups) still goes through Find-Surface-Decide regardless of mode.

### Violation Example

Seeing a function with `user_data: Any` return type while modifying the same file, and silently changing it to `dict[str, str]` instead of surfacing the type-hint gap to the user as a side-finding.

### Enforcement

- **Reviewer** rejects diffs containing changes outside the stated task scope when `scope_mode = "surgical"`
- **Reviewer** allows in-file mechanical cleanups when `scope_mode = "boyscout"` is set

---

## Rule 5: Read Module Documentation Before Implementation

**BEFORE implementing ANY feature, read relevant MODULE.md files.**

### Why It Matters

Failure leads to duplicate systems (creating a Logger when obslog exists), models in the wrong service (UserMeta in licences instead of identity), and circular dependencies.

### Required Reading

1. `app/core/MODULE.md` — Shared services and capabilities
2. `app/services/<target-service>/MODULE.md` — Target service
3. `app/services/<dependency-service>/MODULE.md` — Dependencies

### What to Look For

- **Existing capabilities** — Don't recreate what exists
- **Domain boundaries** — Where does this feature belong?
- **Integration patterns** — How do services communicate?
- **External service patterns** — Factory, singleton, DI?

### Violation Example

Creating a new `EmailService` in your module when `app/core/external/email/` already provides a factory-based email backend.

### Enforcement

- **Implementer** must present MODULE.md findings before coding
- **Reviewer** must verify module documentation was consulted

---

## Rule 6: Extend Base Entity Classes

**ALL entities MUST extend base classes from `app/core/domain/base_entity.py`.**

### Why It Matters

Ensures consistent ID generation, automatic soft-delete handling, standardized timestamps, and type-safe repository operations.

### Base Class Selection Matrix

**Step 1 — Choose ID Type:**

| Question | Answer | ID Type |
|----------|--------|---------|
| Is entity exposed via API responses? | Yes | **UUID** — Never expose internal int IDs externally |
| Is entity internal-only (junction/mapping table)? | Yes | **Int** — Simpler, more efficient for internal use |

**Step 2 — Choose Soft Delete:**

| Question | Answer | Soft Delete |
|----------|--------|-------------|
| Contains sensitive or auditable data? | Yes | **WithSD** — Preserve for compliance/recovery |
| Referenced by other entities? | Yes | **WithSD** — Prevent orphaned references |
| Simple mapping/junction table? | Yes | **Without** — Hard delete is acceptable |
| Data can be recreated if deleted? | Yes | **Without** — No need to preserve |

### Base Classes

| Class | ID Type | Soft Delete | Use Case |
|-------|---------|-------------|----------|
| `BaseUUIDEntityWithSD` | UUID | Yes | API-exposed entities with sensitive data |
| `BaseUUIDEntity` | UUID | No | API-exposed entities, simple/recreatable |
| `BaseIntEntityWithSD` | int | Yes | Internal junction tables needing audit trail |
| `BaseIntEntity` | int | No | Internal junction/mapping tables |

```python
# User — API-exposed, sensitive data
class User(BaseUUIDEntityWithSD, table=True): ...

# AuditLog — API-exposed, immutable
class AuditLog(BaseUUIDEntity, table=True): ...

# UserRole — Internal mapping, no sensitive data
class UserRole(BaseIntEntity, table=True): ...

# ClientRelative — Junction with audit needs
class ClientRelative(BaseIntEntityWithSD, table=True): ...
```

### Violation Example

```python
# WRONG: No base class, redeclares standard fields
class Photo(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: datetime
    deleted_at: datetime | None
```

### Enforcement

- **Implementer** must verify entity base class selection
- **Reviewer** must reject entities without proper base class inheritance

---

## Rule 7: Validate User Scope in Repositories

**Implement role-based data filtering in all repositories.**

### Why It Matters

Security: prevents unauthorized data access. RBAC enforcement at the data layer. Graceful degradation for unknown scopes (empty result, not crash).

### Scope Levels

| Scope | Access Level | Example |
|-------|-------------|---------|
| `SYSTEM` | All data across all domains | Super admin |
| `DOMAIN` | All data within a domain | Domain admin |
| `ORGANIZATION` | All data within an organization | Org admin |
| `SUPPORT` | Read-only access to organization | Support staff |
| `RELATIVE` | Only related client data | Family member |

### Implementation Pattern

```python
def get_resources(self, scope: ScopeContext) -> list[Resource]:
    query = select(Resource)

    if scope.scope == RoleScope.SYSTEM:
        pass  # No filter
    elif scope.scope == RoleScope.ORGANIZATION:
        query = query.where(Resource.organization_id == scope.context_id)
    else:
        logger.warning(f"Unsupported scope: {scope.scope}")
        return []  # Graceful degradation

    return list(self.session.scalars(query))
```

### Violation Example

A repository `list_all()` method that returns all records without any scope filtering — every user sees everything.

### Enforcement

- **Implementer** must add scope validation to all repository query methods
- **Reviewer** must verify scope-based filtering is present

---

## Rule 8: Services Never Access Database Directly

```
NO SESSION IMPORTS IN SERVICES. NO EXCEPTIONS.
```

**Services MUST use repositories for ALL data access. No exceptions.**

### Why It Matters

Clean Architecture: services live in the Application layer, DB access in Infrastructure. Testability: mock repositories, not database sessions. Single Responsibility: repositories own data access logic.

### Forbidden in Services

```python
# FORBIDDEN — Direct Session import
from sqlmodel import Session, select

# FORBIDDEN — Direct query in service
class PhotoService:
    def get_photo(self, photo_id: UUID):
        return self.session.scalars(select(Photo).where(...))

# FORBIDDEN — Direct commit in service
    def save_photo(self, photo: Photo):
        self.session.add(photo)
        self.session.commit()

# FORBIDDEN — Accessing repository internals
    def hack(self):
        self.photo_repo._session.execute_query(...)
```

### Required Pattern

```python
class PhotoService:
    def __init__(
        self,
        photo_repo: PhotoRepositoryInterface,
        album_repo: AlbumRepositoryInterface,
    ):
        self.photo_repo = photo_repo
        self.album_repo = album_repo

    def get_photo(self, photo_id: UUID) -> Photo:
        return self.photo_repo.get_by_id(photo_id)
```

### Violation Example

A service method that calls `self.repo._session.commit()` instead of using a repository method.

### Enforcement

- **Reviewer** must reject any service importing `Session`, `select`, or accessing `._session`

---

## Rule 9: API Docs & Test Alignment

**Every HTTP status code in API `responses={}` MUST be documented AND tested.**

### Why It Matters

Prevents documentation drift (docs say X, tests verify Y). Ensures test coverage matches API contract. Catches missing error handling early.

### Two-Step Verification

| Step | Check | Block if |
|------|-------|----------|
| **1. API Docs Complete** | All status codes have `responses={}` entry with description + example | Missing 401/403/404/409/422 |
| **2. Tests Aligned** | Each documented status code has corresponding test | Documented codes > test count |

### Required Documentation

```python
@router.post("/{id}/upload", responses={
    200: {"description": "Success", "model": ResponseModel},
    401: {"description": "Not authenticated"},
    403: {"description": "Insufficient permissions"},
    404: {"description": "Resource not found"},
    409: {"description": "Conflict — already exists"},
    422: {"description": "Validation error"},
})
```

### Required Tests

For EACH status code above, a test MUST exist covering:
- Success case (200/201/204)
- No auth token (401)
- Wrong permission scope (403)
- Non-existent ID (404)
- Duplicate resource (409)
- Invalid input (422)

### Violation Example

An endpoint with `responses={200: ..., 404: ...}` but no test for the 404 case.

### Enforcement

- **Implementer** writes inline API docs with `responses={}`
- **Tester** reads `responses={}`, creates test per status code
- **Reviewer** verifies docs complete + tests aligned

---

## Rule 10: Refactoring Verification

**During ANY refactoring, ALWAYS verify no features, context, or useful comments were lost.**

### Why It Matters

Refactoring can silently drop important context. Comments explaining "why" are often lost during restructuring. Features hidden in conditional logic can be accidentally removed.

### Required Verification Process

After ANY refactoring task:

1. **Section/Feature Verification** — Every original section/feature must exist somewhere in the refactored code
2. **Key Concept Preservation** — Critical terms, warnings, and design decisions are preserved
3. **Comment Preservation** — "Why" comments, edge case notes, security warnings kept or improved

### Ripple Effect Verification

All affected modules, methods, and documentation MUST be updated:

| Change Type | Must Update |
|-------------|-------------|
| Renamed function/class | All call sites, imports, tests, docs |
| Changed method signature | All callers, mocks in tests, API docs |
| Moved file/module | All imports, MODULE.md, `__init__.py` exports |
| Changed interface/protocol | All implementations, dependency injections |
| Renamed field/parameter | All usages, DTOs, API examples, tests |

### Ripple Effect Checklist

```markdown
### Code Updates
- [ ] All call sites updated
- [ ] All imports updated
- [ ] All tests updated (unit, integration, E2E)
- [ ] All mocks/fixtures updated

### Documentation Updates
- [ ] MODULE.md updated (if service changed)
- [ ] API docs updated (if endpoints changed)
- [ ] .env.example updated (if config changed)

### Validation
- [ ] pyright passes
- [ ] ruff passes
- [ ] All tests pass
```

**Verification gate** — before claiming refactoring complete:
1. RUN: quality gates from `.devt/rules/quality-gates.md` (ruff, pyright, pytest)
2. READ: Full output
3. VERIFY: Zero failures, zero new warnings
4. CHECK: Every file that imported the refactored code still works
5. ONLY THEN: Claim refactoring is complete

### Violation Example

Renaming `UserService.authenticate()` to `UserService.verify_credentials()` but forgetting to update the mock in `test_login.py` and the import in `routes.py`.

### Enforcement

- **Implementer** must provide refactoring verification report
- **Reviewer** must reject if features/context lost or affected code not updated

---

## Rule 11: No TODO Comments, No Placeholders, No Temporal Markers

```
NO INCOMPLETE CODE. NO PLACEHOLDERS. NO TEMPORAL MARKERS.
```

**All code must be complete and functional. No deferred work markers.**

### Why It Matters

TODOs create a false sense of progress — the feature looks done but isn't. Placeholders get shipped to production. Temporal markers clutter code with version-management information that belongs in git history.

### Forbidden Patterns

```python
# FORBIDDEN — TODO comments
# TODO: Add error handling
# FIXME: This doesn't handle edge cases

# FORBIDDEN — Placeholder implementations
def process_payment(self) -> None:
    pass  # Will implement later

# FORBIDDEN — Temporal markers
class UserResponse:  # (NEW)
    """User response model (UPDATED 2024-03-15)"""

def test_login_fixed():  # v2, FIXED
    ...
```

### Correct Approach

- Implement the feature completely or don't start it
- If a dependency is missing, create it immediately
- Describe WHAT something does, not WHEN it was added
- Git history tracks changes — code describes current state

### Violation Example

A test named `test_photo_upload_new` or a comment `# NEW: added for v2.3`.

### Enforcement

- **Reviewer** must reject any code containing TODOs, placeholders, or temporal markers

---

## Rule 12: No Completion Claims Without Verification

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.
```

**Why**: Agents claim "done" without running verification. "Should work" and "I'm confident" are not evidence. Only command output is evidence.

**Gate function** — before claiming ANY status (DONE, fixed, passing):
1. IDENTIFY: What command proves this claim?
2. RUN: Execute the FULL command (fresh, not cached)
3. READ: Full output — check exit code, count failures
4. VERIFY: Does output confirm the claim?
5. ONLY THEN: Make the claim WITH evidence

**Red flags** (thoughts that mean STOP and run the command):
- "Should work now"
- "I'm confident this is correct"
- "The tests should pass"
- "Linter was clean last time"
- "Just this once, skip verification"

| Excuse | Reality |
|--------|---------|
| "I just wrote it, it should work" | Code you just wrote is the most likely to be wrong |
| "The test passed earlier" | Earlier ≠ now. Run it again. |
| "Only changed one line" | One line can break everything. Verify. |
| "Under time pressure" | Shipping broken code wastes more time than verifying |

**Enforcement**: ALL agents. Verifier agent specifically checks this.


---

## Pre-Flight Protocol

Before any non-trivial change, the **Two-Tier Pre-Flight Protocol** applies (see `${CLAUDE_PLUGIN_ROOT}/guardrails/golden-rules.md` Rule 14):

- **Tier 1 (Topic)**: dev workflows auto-fire `/devt:preflight "<task>"` at context_init, writing `.devt/state/preflight-brief.md`. Read the Brief FIRST — it lists every governing ADR/Concept/Flow + REJ tombstones for your task.
- **Tier 2 (File)**: before each Edit/Write, append a `PREFLIGHT <ts> edit <file> :: <governing IDs or 'no governance'>` line to `.devt/state/scratchpad.md`. The PreToolUse `pre-flight-guard` hook checks this — `memory.preflight_mode: block` denies the edit otherwise.

Project ADRs in `.devt/memory/decisions/` are **constitutional** — they override generic principles. Check `node bin/devt-tools.cjs memory affects <file>` if your edit isn't covered by the current Brief; run `/devt:preflight` again on scope expansion.
