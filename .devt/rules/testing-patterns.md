# Testing Patterns — Python / FastAPI

## Reference Files

| File | Purpose |
|------|---------|
| `hurl-test-checklist.md` | Pre-flight checklist — complete BEFORE writing HURL tests |
| `hurl-reference.md` | Full HURL reference: metadata, variable capture, token flows, debugging |
| `hurl-registration.md` | Test file registration: naming, metadata.json, execution order |
| `pytest-reference.md` | pytest patterns: mocking strategy (max 3 mocks), async, fixtures, integration |

## Test Pyramid

1. **E2E tests** (HURL or similar) — primary validation of API contracts
2. **Integration tests** — hit real database, verify repository + service interaction
3. **Unit tests** — isolated business logic, fast feedback

## TDD Workflow (Red-Green-Refactor)

When implementing new features or fixing bugs, consider test-first development:

### RED: Write Failing Test
1. Write a test that captures the expected behavior
2. Run it — it MUST fail
3. If it passes: the feature already exists OR your test is wrong. Investigate.

### GREEN: Make It Pass
1. Write the MINIMAL code to make the test pass
2. No cleverness. No future-proofing. Just pass the test.
3. Run the test — it MUST pass now

### REFACTOR: Clean Up (only if needed)
1. Improve code (naming, structure, DRY)
2. Run ALL tests — they MUST still pass
3. If tests break: undo the refactor. Working > clean.

### Why TDD?
- A test that passes immediately proves nothing — you need to see it fail first
- Minimal implementation prevents over-engineering
- Refactoring with tests is safe; without tests is gambling

| Excuse | Reality |
|--------|---------|
| "Too simple for TDD" | Simple code benefits most — fast RED-GREEN cycle |
| "I know what I'm building" | TDD tests your spec, not your confidence |
| "Tests slow me down" | TDD prevents debugging later. Net time saved. |

---

## Regression Test Pattern

When fixing a bug:
1. Write a test that reproduces the bug
2. Run it — MUST fail (proves the test catches the bug)
3. Apply the fix
4. Run it — MUST pass
5. Revert the fix temporarily — MUST fail again (proves causation)
6. Re-apply the fix and commit

This proves your test actually catches the specific bug, not something else.

---

## Frameworks & Tools

- `pytest` for all test types (configure in `pyproject.toml`, not `pytest.ini`)
- HURL for E2E HTTP workflow tests (or equivalent HTTP testing tool)
- Real PostgreSQL for integration tests — never mock the database
- `testcontainers` for ephemeral test databases in CI (no docker-compose dependency)
- `httpx.AsyncClient` with `ASGITransport` for async endpoint testing
- `polyfactory` for auto-generating test data from Pydantic/SQLAlchemy models
- `unittest.mock` for unit tests — minimal mocking only

## Speed Targets

| Type        | Target  | Scope                       |
| ----------- | ------- | --------------------------- |
| Unit        | < 1 min | Service logic, domain rules |
| Integration | < 3 min | Repository + real DB        |
| E2E         | < 5 min | Full HTTP request/response  |

## Mocking Rules

- Maximum 3 mocks per unit test — more indicates poor design
- Mock at boundaries only (repository interfaces, external APIs)
- Never mock the thing under test
- Integration tests use real database — no mocking data access
- Services mock repositories; repositories test against real DB

## File Naming & Organization

- Test files: `test_<module>.py` or `test_<feature>.py`
- Test directories mirror source structure
- Each service has its own `tests/` directory with `unit/` and `integration/` subdirs
- Shared fixtures in `conftest.py` at appropriate scope level

## Test Structure

- Arrange / Act / Assert pattern — clearly separated sections
- One assertion concept per test (multiple asserts on same object are fine)
- Descriptive test names that explain the scenario and expected behavior
- No temporal markers in test names — describe WHAT, not WHEN

## Coverage Requirements

- Every public function must have tests
- Edge cases: empty inputs, boundary values, error conditions
- Error paths: verify correct exception types and messages
- No placeholder tests — every test must assert meaningful behavior

## Integration Test Patterns

- Use test database with migrations applied
- Each test gets a clean transaction (rollback after test)
- Test data created via `polyfactory` or fixtures — never rely on seed data
- Verify actual database state, not just return values
- Use `testcontainers` for ephemeral databases in CI:

```python
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def db_url():
    with PostgresContainer("postgres:16") as pg:
        yield pg.get_connection_url()
```

### Async Endpoint Testing

Use `httpx.AsyncClient` with `ASGITransport` for true async testing:

```python
from httpx import ASGITransport, AsyncClient

@pytest.mark.anyio
async def test_create_item(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/items", json={"name": "test"})
        assert response.status_code == 201
```

`TestClient` (sync) is fine for sync route handlers. Use `AsyncClient` when routes use `async def`.

## E2E Test Patterns

- Test complete user workflows, not individual endpoints
- Verify response status codes, headers, and body structure
- Chain requests: create -> read -> update -> delete
- Test authentication and authorization scenarios
- Validate error responses match API contract

## What NOT to Test

- Framework internals (FastAPI routing, Pydantic validation)
- Third-party library behavior
- Trivial getters/setters with no logic
- Private methods directly — test through public interface

---

## HURL E2E as Primary Validation

HURL E2E tests are the PRIMARY validation mechanism for API endpoints — they verify the complete HTTP contract including status codes, response shapes, and error handling.

**Before writing any HURL tests**, complete the coverage checklist in `.devt/rules/hurl-test-checklist.md` for each endpoint. The checklist forces analysis of the actual endpoint signature (path params, query params, request body) and ensures one test per scenario.

### Directory Structure

```
tests/hurl/
├── TEMPLATE.hurl.example   # MANDATORY template for new tests
├── {letter}{nn}_{name}.hurl # Domain-prefixed test files
├── .env.hurl               # Hurl test variables
├── metadata.json           # Execution order + phase labels
└── scripts/
    └── validate_hurl.sh    # Validate files for dashboard compatibility
```

### File Naming Convention

**Pattern:** `{letter}{nn}_{name}.hurl` (domain-prefixed naming)

- **Letter** (a-z) = domain group — identifies which service/area the test covers
- **Number** (01-99) = order within domain — tens digit groups related sub-topics
- **Name** = descriptive snake_case name

```
a01_health_probes.hurl        # Infrastructure
b01_auth_setup.hurl           # Auth & Identity
c01_client_relationships.hurl # Clients
d01_licenses.hurl             # Licenses
e01_user_api.hurl             # User Profile
```

### Creating New HURL Test Files

Always copy the official template:

```bash
cp tests/hurl/TEMPLATE.hurl.example tests/hurl/{letter}{nn}_{feature_name}.hurl
```

### Metadata Requirements (Per-Entry)

Every HTTP request MUST have metadata comments:

```hurl
# @ACTOR: System Admin (SYSTEM:MANAGE permission)
# @EXPECTED: 201 Created with resource UUID
# @CONTEXT: Creating a new resource for testing
# @WHY: Resources must exist before assignment

POST {{base_url}}/api/v1/resources
Authorization: Bearer {{admin_token}}
Content-Type: application/json
{
    "name": "Test Resource"
}
HTTP 201
[Captures]
resource_uuid: jsonpath "$.id"
```

**Required Tags:**

| Tag | Required | Description |
|-----|----------|-------------|
| `@ACTOR:` | Yes | Who performs the action (role + permission) |
| `@EXPECTED:` | Yes | Expected HTTP status and outcome |
| `@CONTEXT:` | Yes | What this test is about |
| `@WHY:` | Recommended | Business reason for this test |
| `@CAPTURES:` | Optional | Variables captured from response |

### File-Level Headers

Each `.hurl` file must have these headers:

- `@NAME` — Short test file name
- `@DESCRIPTION` — What this file tests
- `@MODULE` — Which service module
- `@COVERS` — Which endpoints are covered

### Required Test Cases per Endpoint

| Case Type | HTTP Status | Required |
|-----------|-------------|----------|
| Success | 200/201/204 | Yes |
| Validation Error | 422 | Yes |
| Auth Error | 401 | Yes |
| Permission Error | 403 | Yes |
| Not Found | 404 | For GET/PUT/DELETE |

### Validation

Run validation automatically — never ask the user:

```bash
# Syntax validation
hurlfmt --check <file>

# Metadata + structure validation
bash tests/hurl/scripts/validate_hurl.sh <file>

# Validate all enabled files
bash tests/hurl/scripts/validate_hurl.sh --all
```

### Phase-Based Organization

Organize tests in logical phases within each file:

```hurl
# PHASE 1: Setup — Create dependencies
# PHASE 2: CRUD Operations — Create, Read, Update, Delete
# PHASE 3: Error Cases — 401, 403, 404, 422 scenarios
# PHASE 4: Cleanup — Delete created resources in reverse order
```

---

## Soft-Delete Testing

Soft-deleted records appearing in GET/LIST responses is a common bug. Using `session.get()` bypasses soft-delete filters. Tests MUST verify this behavior.

### HURL Pattern

Every entity with soft-delete (extends `BaseUUIDEntityWithSD`) MUST have these tests:

```hurl
# Soft-delete the resource
DELETE {{base_url}}/api/v1/resources/{{resource_uuid}}
Authorization: Bearer {{user_token}}
HTTP 204

# GET on soft-deleted resource returns 404
GET {{base_url}}/api/v1/resources/{{resource_uuid}}
Authorization: Bearer {{user_token}}
HTTP 404

# List excludes soft-deleted resource
GET {{base_url}}/api/v1/resources
Authorization: Bearer {{user_token}}
HTTP 200
[Asserts]
jsonpath "$.items[?(@.id == '{{resource_uuid}}')]" count == 0
```

### Pytest Pattern

```python
@pytest.mark.integration
def test_get_by_id_excludes_soft_deleted(db_session, sample_entity):
    """Verify get_by_id returns None for soft-deleted records."""
    repo = MyEntityRepository(db_session)
    entity = repo.create(sample_entity)
    repo.delete(entity.id, deleted_by=uuid4())
    db_session.commit()

    result = repo.get_by_id(entity.id)
    assert result is None, "Soft-deleted record should not be returned by get_by_id"


@pytest.mark.integration
def test_list_all_excludes_soft_deleted(db_session, sample_entities):
    """Verify list_all excludes soft-deleted records by default."""
    repo = MyEntityRepository(db_session)
    entities = [repo.create(e) for e in sample_entities]
    repo.delete(entities[0].id)
    db_session.commit()

    results = repo.list_all()
    assert len(results) == len(entities) - 1
    assert entities[0].id not in [r.id for r in results]


@pytest.mark.integration
def test_restore_soft_deleted_record(db_session, sample_entity):
    """Verify restore makes record accessible again."""
    repo = MyEntityRepository(db_session)
    entity = repo.create(sample_entity)
    repo.delete(entity.id)
    db_session.commit()

    repo.restore(entity.id)
    db_session.commit()

    result = repo.get_by_id(entity.id)
    assert result is not None
    assert result.deleted_at is None
```

### Permanent Delete Testing

Test both soft delete and permanent (hard) delete:

```python
@pytest.mark.integration
def test_permanent_delete_removes_from_db(db_session, sample_entity):
    """Verify delete_hard permanently removes the record."""
    repo = MyEntityRepository(db_session)
    entity = repo.create(sample_entity)
    repo.delete_hard(entity.id)
    db_session.commit()

    # Even direct query should return nothing
    result = repo.get_by_id(entity.id)
    assert result is None
```

### Anti-Pattern: Using session.get()

```python
# WRONG: session.get() bypasses soft-delete filter
def get_by_id(self, entity_id: UUID) -> MyEntity | None:
    return self.session.get(MyEntity, entity_id)  # Returns soft-deleted!

# CORRECT: Explicit query with filter
def get_by_id(self, entity_id: UUID) -> MyEntity | None:
    statement = select(MyEntity).where(
        MyEntity.id == entity_id,
        MyEntity.deleted_at.is_(None),
    )
    return self.session.scalars(statement).first()
```

### Soft-Delete Coverage Checklist

Every repository for soft-delete entities MUST have tests for:

- [ ] `get_by_id()` returns `None` for soft-deleted records
- [ ] `get_by_ids()` excludes soft-deleted records
- [ ] `list_all()` excludes soft-deleted records by default
- [ ] `count()` excludes soft-deleted records
- [ ] `delete()` sets `deleted_at` (not hard delete)
- [ ] `restore()` clears `deleted_at` and makes record accessible
- [ ] API GET returns 404 after soft-delete (E2E test)
- [ ] API LIST excludes soft-deleted records (E2E test)

---

## Integration Test Patterns

### Hit REAL Database

Integration tests must hit a real database — never mock repositories:

```python
@pytest.mark.integration
def test_user_repository_creates_user(db_session):
    """Integration test with real database."""
    repo = UserRepository(db_session)
    user = repo.create(email="test@example.com", name="Test")
    assert user.id is not None
```

### Use Test Data Factories

Create test data via factories or fixtures — never rely on seed data:

```python
@pytest.fixture
def sample_user(db_session):
    """Create a real user in test database."""
    user = User(email="test@example.com", name="Test User")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user
```

### Full State Reset Between Tests

Each test gets a clean transaction — rollback after test:

```python
@pytest.fixture
def db_session(test_engine):
    """Create test database session with rollback."""
    with Session(test_engine) as session:
        yield session
        session.rollback()
```

### Maximum 3 Mocks per Unit Test

If more than 3 mocks are needed:
- The code may have too many dependencies — refactor
- The test should be an integration test instead
- Always provide justification if approaching the limit

### What to Mock

| Category | Mock? | Examples |
|----------|-------|---------|
| External APIs | Yes | Email, SMS, push notification services |
| Time/date | Yes | `datetime.now()` |
| Repositories | Yes (unit) / No (integration) | Unit tests mock via interfaces. Integration tests use real DB. |
| Internal services | Avoid | May indicate tight coupling |

---

## Token/Async Flow Testing

### Email Token Extraction

For tests requiring tokens from async email operations (verification, password reset):

1. Server sends email via `MemoryEmailBackend` — tokens stored in-memory
2. Test queries a testing endpoint to retrieve the token
3. Token captured as variable for use in subsequent requests

```hurl
# Trigger email sending
POST {{base_url}}/api/v1/auth/forgot-password
Content-Type: application/json
{ "email": "user@example.com" }
HTTP 200

# Retrieve token from test mailbox
GET {{base_url}}/api/v1/testing/email-tokens/user@example.com
HTTP 200
[Captures]
reset_token: jsonpath "$.tokens[-1].token"

# Use captured token
POST {{base_url}}/api/v1/auth/reset-password
Content-Type: application/json
{
    "token": "{{reset_token}}",
    "new_password": "NewSecure123!"
}
HTTP 200
```

### SMS Verification Code Capture

For SMS 2FA tests:

```hurl
# Trigger SMS code
POST {{base_url}}/api/v1/auth/2fa/enable
Authorization: Bearer {{user_token}}
Content-Type: application/json
{ "delivery_method": "sms" }
HTTP 200

# Retrieve code from test SMS backend
GET {{base_url}}/api/v1/testing/sms-code/+31612345678
HTTP 200
[Captures]
sms_code: jsonpath "$.code"

# Use captured code
POST {{base_url}}/api/v1/auth/2fa/verify
Content-Type: application/json
{
    "partial_token": "{{partial_token}}",
    "code": "{{sms_code}}"
}
HTTP 200
```

### Configuration for Test Backends

```bash
# .env.test
EMAIL_BACKEND=["memory"]   # Required for email token capture
SMS_BACKEND=["memory"]     # Required for SMS code capture
PUSH_BACKEND=["memory"]    # Required for push notification assertions
```

### Variable Capture and Chaining in HURL

```hurl
# Capture UUID from creation response
POST {{base_url}}/api/v1/users
Authorization: Bearer {{admin_token}}
Content-Type: application/json
{ "email": "test@example.com", "name": "Test" }
HTTP 201
[Captures]
user_id: jsonpath "$.id"

# Use captured value in subsequent request
GET {{base_url}}/api/v1/users/{{user_id}}
Authorization: Bearer {{admin_token}}
HTTP 200
[Asserts]
jsonpath "$.id" == "{{user_id}}"
```

### Common Assertions

```hurl
# JSON assertions
[Asserts]
jsonpath "$.id" exists
jsonpath "$.name" == "Expected Name"
jsonpath "$.items" count == 5
jsonpath "$.total" >= 0
jsonpath "$.is_active" == true
jsonpath "$.created_at" isString

# Header assertions
header "Content-Type" contains "application/json"

# JSONPath for first/last items
jsonpath "$.tokens[0].token"   # First
jsonpath "$.tokens[-1].token"  # Last (NO slice notation — use negative index)
```
