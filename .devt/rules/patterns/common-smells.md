# Common Code Smells — Python / FastAPI

Anti-patterns to detect and fix during code review and development.

## Inline Imports

**Smell**: Imports inside function bodies instead of at module top level.

**Why it's bad**: Indicates circular dependencies — a structural design problem.

**How to detect**:
```bash
grep -rn "^\s\+import \|^\s\+from .* import" app/ --include="*.py" | grep -v "^.*:1:" | grep -v "__init__"
```

**Fix**: Refactor to eliminate the circular dependency. Move shared logic to the correct layer or introduce an interface.

## God Services

**Smell**: Service class with 1000+ lines or 25+ methods.

**Why it's bad**: Violates single responsibility. Hard to test, hard to understand.

**How to detect**:
```bash
# Find service files over 500 lines
wc -l app/services/*/application/service.py | sort -rn | head -10
# Count methods per service
grep -c "def " app/services/*/application/service.py | sort -t: -k2 -rn | head -10
```

**Fix**: Extract focused sub-services. Group related methods into their own service class with a clear responsibility boundary.

## N+1 Queries

**Smell**: Database call inside a loop (`for item in items: repo.get(item.id)`).

**Why it's bad**: Linear DB round-trips. 100 items = 100 queries.

**How to detect**:
```bash
# Look for repo/DB calls inside for loops
grep -B 3 "repo\.\|repository\.\|session\." app/ -rn --include="*.py" | grep "for .* in"
```

**Fix**: Use batch queries (`get_by_ids()`), eager loading, or JOINs in the repository.

## Missing Base Class Inheritance

**Smell**: Entity models that don't extend the project's base entity classes.

**Why it's bad**: Missing standard fields (id, timestamps, soft-delete). Inconsistent behavior across entities.

**How to detect**:
```bash
grep -rn "class.*SQLModel.*table=True" app/ --include="*.py" | grep -v "BaseUUID\|BaseInt"
```

**Fix**: All entities must extend the appropriate base class (UUID base for API-exposed, Int base for internal).

## Direct Session Access in Services

**Smell**: Service importing `Session`, calling `session.execute()`, or accessing `repo._session`.

**Why it's bad**: Violates repository pattern. Business logic coupled to database internals.

**How to detect**:
```bash
grep -rn "from sqlmodel import.*Session\|from sqlalchemy.*import.*Session" app/services/*/application/ --include="*.py"
grep -rn "session\.\|_session\." app/services/*/application/ --include="*.py"
```

**Fix**: Add the needed method to the repository interface and implementation. Services only call repository methods.

## Raw SQL in Services

**Smell**: SQL strings or `text()` calls in service layer code.

**Why it's bad**: Data access logic belongs in repositories. Services should express business intent, not query mechanics.

**How to detect**:
```bash
grep -rn "text(\|\.execute(" app/services/*/application/ --include="*.py"
grep -rn "select(\|insert(\|update(\|delete(" app/services/*/application/ --include="*.py"
```

**Fix**: Move the query to the repository. Expose a domain-meaningful method name on the repository interface.

## Generic Exception Swallowing AppError

**Smell**: `except Exception` catching both domain errors and unexpected failures.

```python
# BAD
try:
    result = service.do_something()
except Exception:
    return JSONResponse(status_code=500, ...)
```

**Why it's bad**: Domain exceptions (NotFoundError, ConflictError) get swallowed and returned as 500 instead of their proper status codes.

**How to detect**:
```bash
grep -rn "except Exception" app/ --include="*.py" | grep -v "except Exception as\|# noqa"
```

**Fix**: Catch `AppError` first and re-raise, then handle generic `Exception`:

```python
# GOOD
try:
    result = service.do_something()
except AppError:
    raise  # Let centralized handler map to correct HTTP status
except Exception:
    return JSONResponse(status_code=500, ...)
```

## Deep Nesting

**Smell**: 4+ levels of indentation from nested if/for/try blocks.

**Why it's bad**: Hard to read, hard to test individual branches, high cognitive load.

**How to detect**:
```bash
# Find lines with 4+ levels of indentation (16+ spaces)
grep -rn "^                " app/ --include="*.py" | grep "if \|for \|while \|try:" | head -20
```

**Fix**: Use early returns (guard clauses), extract helper functions, flatten control flow.

## uuid4 Usage

**Smell**: `uuid.uuid4()` for generating entity IDs.

**Why it's bad**: Random UUIDs have poor B-tree locality, are not time-sortable.

**How to detect**:
```bash
grep -rn "uuid4\|uuid\.uuid4\|from uuid import.*uuid4" app/ --include="*.py"
```

**Fix**: Use UUIDv7 (`uuid_utils.uuid7()` or project wrapper `generate_uuid()`). Time-ordered, RFC 9562 compliant, better database performance.

---

## Clean Architecture Layer Violations

**Smell**: Inner layer importing from outer layer (domain importing from API or infrastructure).

**What it looks like**:
```python
# File: app/services/photos/domain/entities.py
from app.services.photos.api.v1.schemas import PhotoCreateRequest  # WRONG
from app.services.photos.infrastructure.models import PhotoModel    # WRONG
```

**Why it's bad**: Violates the dependency rule of Clean Architecture. Inner layers must not know about outer layers. Creates tight coupling and makes domain logic untestable without infrastructure.

**How to detect**:
```bash
# Domain importing from API or infrastructure
grep -r "from.*api\." app/services/*/domain/
grep -r "from.*infrastructure" app/services/*/domain/

# Routes importing infrastructure directly
grep -r "from.*infrastructure" app/services/*/api/
```

**How to fix**: Domain is pure Python with no external dependencies. Application layer depends only on domain. Infrastructure implements application interfaces. API depends on application through DTOs and services.

---

## Business Logic in Repositories

**Smell**: Repository methods containing conditional business rules, pricing calculations, permission checks, or workflow decisions.

**What it looks like**:
```python
class OrderRepository:
    def create_order(self, order: Order) -> Order:
        # Business logic in repository!
        if order.total > 1000:
            order.discount = 0.1
        if order.user.is_premium:
            order.priority = "high"
        self.session.add(order)
        self.session.commit()
        return order
```

**Why it's bad**: Repositories should be pure data access (CRUD). Business rules become untestable without a database and are duplicated when multiple services need the same logic.

**How to detect**:
```bash
# Look for if/else logic in repository files
grep -n "if.*:" app/services/*/infrastructure/repositories.py | grep -v "if.*is_(None)\|if not\|if filters"
```

**How to fix**: Move all conditional business logic to the service layer. Repositories expose `add()`, `get_by_id()`, `update()`, `delete()` — no business decisions.

---

## Business Logic in Routes (Thin Router Violation)

**Smell**: Route handler with more than ~10 lines of business logic, multiple conditional branches, or direct data manipulation.

**What it looks like**:
```python
@router.post("/photos")
async def upload_photo(request: PhotoRequest, session: Session = Depends()):
    # 30+ lines of business logic in route handler
    if user.license_type == "premium":
        max_photos = 1000
    else:
        max_photos = 100
    current_count = session.scalars(select(func.count(Photo.id))...).one()
    if current_count >= max_photos:
        raise HTTPException(...)
    # More complex logic...
```

**Why it's bad**: Routes should be thin dispatchers. Business logic in routes is hard to test (requires HTTP client), hard to reuse, and violates Clean Architecture.

**How to detect**:
```bash
# Route files importing Session or select (should only import services)
grep -rn "from sqlmodel import\|from sqlalchemy import" app/services/*/api/ --include="*.py"
# Route files with many lines per function (>15 lines between def and next def/class)
grep -c "if \|for \|while " app/services/*/api/v1/routes.py
```

**How to fix**: Extract all business logic to a service. Route becomes:
```python
@router.post("/photos")
async def upload_photo(request: PhotoRequest, service: PhotoService = Depends()):
    return service.upload_photo(request)
```

---

## Circular Dependencies Between Modules

**Smell**: Service A imports from Service B and Service B imports from Service A.

**What it looks like**:
```python
# In photos/service.py
from app.services.licences.service import LicenceService

# In licences/service.py
from app.services.photos.service import PhotoService  # Circular!
```

**Why it's bad**: Creates import errors, tight coupling, and makes both services impossible to test independently.

**How to detect**:
```bash
# For each service, check if it imports from services that import it back
for svc in app/services/*/; do
    echo "=== $(basename $svc) imports ==="
    grep -r "from app.services" "$svc" --include="*.py" | grep -v tests | grep -v "$(basename $svc)"
done
```

**How to fix**: Both services should depend on interfaces/abstractions, not concrete implementations. Use dependency injection and repository interfaces. If circular, introduce a shared interface or orchestrate through a mediator service.

---

## Hardcoded Secrets in Code

**Smell**: API keys, passwords, or tokens as string literals in source code.

**What it looks like**:
```python
PUSHY_API_KEY = "sk_live_abc123..."
sendgrid_key = "SG.xxxxx"
DATABASE_URL = "postgresql://user:password@host/db"
```

**Why it's bad**: Secrets in source code get committed to version control, shared in code reviews, and exposed in logs.

**How to detect**:
```bash
grep -rn "API_KEY\s*=" app/ --include="*.py"
grep -rn "SECRET\s*=" app/ --include="*.py"
grep -rn "sk_live\|sk_test\|SG\." app/ --include="*.py"
grep -rn "password\s*=" app/ --include="*.py" | grep -v "password_hash\|hashed_password"
```

**How to fix**: All secrets from environment variables via settings. Use `SecretStr` for Pydantic settings fields:
```python
from app.core.config import settings
pushy_key = settings.PUSHY_API_KEY_SECRET.get_secret_value()
```

---

## Sync Operations in Async Functions

**Smell**: Blocking calls (time.sleep, requests.get, file I/O) inside async function bodies.

**What it looks like**:
```python
async def process_data():
    time.sleep(1)  # Blocks entire event loop!

async def fetch_data():
    result = requests.get(url)  # Blocking HTTP client!
```

**Why it's bad**: Blocks the entire event loop, freezing all concurrent requests. One slow sync call can make the entire server unresponsive.

**How to detect**:
```bash
grep -rn "time\.sleep" app/ --include="*.py"
grep -rn "requests\.get\|requests\.post\|requests\.put" app/ --include="*.py"
```

**How to fix**:
```python
# Use async alternatives
import asyncio
async def process_data():
    await asyncio.sleep(1)

import httpx
async def fetch_data():
    async with httpx.AsyncClient() as client:
        result = await client.get(url)
```

---

## Missing Type Hints on Public Functions

**Smell**: Public functions or methods without parameter type annotations or return type.

**What it looks like**:
```python
def get_user(user_id):
    return db.query(User).filter(User.id == user_id).first()
```

**Why it's bad**: No IDE support, no mypy validation, no documentation of expected types. Runtime errors instead of compile-time catches.

**How to detect**:
```bash
# mypy will catch these
uv run mypy app/services/<service>/
```

**How to fix**:
```python
def get_user(user_id: UUID) -> User | None:
    return db.query(User).filter(User.id == user_id).first()
```

---

## Temporal Markers in Names/Comments

**Smell**: `(NEW)`, `(UPDATED)`, `(FIXED)`, `(OLD)`, `_v2`, `_new`, `_updated` in function/class/test names or comments.

**What it looks like**:
```python
class UserResponseV2(BaseModel): ...     # Version suffix
def test_login_fixed(): ...              # Temporal marker
# NEW: Added for release 2.3
# UPDATED: Changed behavior in v2
class EnhancedPhotoService: ...          # Superlative prefix
```

**Why it's bad**: Code is not a changelog. Git tracks when changes were made. Temporal markers create confusion about which version is "current" and accumulate as dead annotations.

**How to detect**:
```bash
grep -rn "(NEW)\|(UPDATED)\|(FIXED)\|(OLD)" app/ --include="*.py"
grep -rn "_v2\|_new\|_updated\|_enhanced\|_improved\|_optimized" app/ --include="*.py"
grep -rn "# NEW:\|# UPDATED:\|# FIXED:" app/ --include="*.py"
```

**How to fix**: Remove temporal markers. Describe WHAT something does, not WHEN it was added. `UserResponseV2` becomes `UserResponse`. `test_login_fixed` becomes `test_login_returns_token`.

---

## Over-Mocking in Tests (>3 Mocks)

**Smell**: Unit test with more than 3 mock objects or mock patches.

**What it looks like**:
```python
def test_process_order(mock_repo, mock_email, mock_sms, mock_payment, mock_inventory):
    # 5 mocks! This test is testing nothing meaningful.
    service = OrderService(mock_repo, mock_email, mock_sms, mock_payment, mock_inventory)
    service.process(order)
```

**Why it's bad**: Over-mocked tests are fragile, test implementation rather than behavior, and provide false confidence. The test passes but the real system might fail.

**How to detect**:
```bash
# Count mocks per test file
grep -c "@patch\|Mock(" app/services/*/tests/*.py
```

**How to fix**: If >3 mocks needed, convert to integration test with real database. Or refactor the code — too many dependencies indicates the class has too many responsibilities.

---

## Missing Assertions in Tests

**Smell**: Test function with no `assert` statements or mock verification.

**What it looks like**:
```python
def test_send_email(mock_sendgrid):
    service = NotificationService(sendgrid=mock_sendgrid)
    service.send_email("test@example.com")
    # No assertions! Test always passes.
```

**Why it's bad**: The test provides zero verification. It runs without error but proves nothing about correctness.

**How to detect**:
```bash
# Look for test functions without assert
grep -A 10 "def test_" app/services/*/tests/*.py | grep -B 5 "^$" | grep "def test_"
```

**How to fix**: Every test must assert meaningful behavior:
```python
def test_send_email(mock_sendgrid):
    service = NotificationService(sendgrid=mock_sendgrid)
    service.send_email("test@example.com")
    mock_sendgrid.send.assert_called_once_with("test@example.com")
```

---

## Repository Cross-Domain Queries

**Smell**: Repository querying another service's domain tables directly instead of going through the owning service's repository.

**What it looks like**:
```python
# In PhotoRepository — querying License table!
class PhotoRepository:
    def get_user_photos_with_license(self, user_id: UUID):
        return self.session.scalars(
            select(Photo, License)
            .join(License, License.user_id == Photo.user_id)
            .where(Photo.user_id == user_id)
        )
```

**Why it's bad**: Violates domain boundaries. Creates hidden coupling between services. Schema changes in one service silently break another.

**How to detect**:
```bash
# Repository files importing other services' models
for svc in app/services/*/; do
    echo "=== $(basename $svc) ==="
    grep -r "from app.services" "$svc/infrastructure/" 2>/dev/null | grep -v "$(basename $svc)"
done
```

**How to fix**: Service orchestrates multiple repositories:
```python
class PhotoService:
    def __init__(self, photo_repo, license_repo):
        self.photo_repo = photo_repo
        self.license_repo = license_repo

    def get_user_photos_with_license(self, user_id: UUID):
        photos = self.photo_repo.get_by_user(user_id)
        license = self.license_repo.get_active(user_id)
        return photos, license
```

---

## Missing Error Class Inheritance (Must Extend AppError)

**Smell**: Custom exception classes that inherit from plain `Exception`, `ValueError`, or `RuntimeError` instead of `AppError`.

**What it looks like**:
```python
class PhotoError(Exception):  # WRONG!
    pass

class PhotoNotFoundError(Exception):  # WRONG!
    pass
```

**Why it's bad**: The centralized error handler maps `AppError` subclasses to proper HTTP status codes. Plain `Exception` returns 500 Internal Server Error regardless of the actual error type.

**How to detect**:
```bash
grep -rn "class.*Exception\)" app/services/ --include="*.py"
grep -rn "class.*ValueError\)" app/services/ --include="*.py"
grep -rn "class.*RuntimeError\)" app/services/ --include="*.py"
# Also check for wrong file naming
find app/services -name "exceptions.py" -type f  # Should be errors.py
```

**How to fix**: Inherit from `AppError` hierarchy:
```python
from app.core.errors import NotFoundError

class PhotoNotFoundError(NotFoundError):
    def __init__(self, photo_id: UUID | None = None, **kwargs):
        super().__init__(resource_name="Photo", resource_id=photo_id, **kwargs)
```

Error file must be named `errors.py` (not `exceptions.py`).

---

## Testing Mock Behavior

**Smell**: Tests assert that a mock exists or was called, rather than testing real behavior.

**Why it's bad**: Proves nothing about production code. Mock call counts are implementation details.

**How to detect**:
```bash
grep -rn "assert.*called\|assert.*call_count\|mock.*assert_called" tests/
```

**How to fix**: Test the actual outcome (return value, state change, side effect) not the mock's call log.

---

## Test-Only Methods in Production

**Smell**: Production classes have methods like `reset()`, `destroy()`, `_test_helper()` that exist solely for test cleanup.

**Why it's bad**: Test infrastructure leaking into production. Creates maintenance burden and potential misuse.

**How to detect**:
```bash
grep -rn "def.*_test\|def.*reset_for_test\|def.*destroy" app/ --include="*.py"
```

**How to fix**: Move cleanup logic to test fixtures or conftest.py. Production classes should not know about tests.

---

## Symptom Fixes

**Smell**: Fixing where the error appears instead of tracing to root cause. Often identified by 3+ sequential fix attempts on the same issue.

**Why it's bad**: Symptoms keep recurring. Each fix adds complexity without solving the real problem.

**How to detect**: Look for patterns in git log:
```bash
git log --oneline | grep -i "fix.*same\|fix.*again\|attempt\|retry"
```

**How to fix**: Stop. Trace the data flow backward from the symptom to the origin. If 3+ fixes failed, the problem is likely architectural — discuss with the team.

---

## Exposed Integer IDs in API Endpoints

**Smell**: API endpoints accepting or returning integer IDs instead of UUIDs.

**What it looks like**:
```python
@router.get("/users/{user_id}")
def get_user(user_id: int):  # Integer ID exposed!
    return service.get_user(user_id)

# Response: {"id": 42, "name": "Test User"}
```

**Why it's bad**: Exposes internal database sequence numbers. Enables enumeration attacks (try id=1, id=2, ...). Reveals system scale. UUIDs prevent this.

**How to detect**:
```bash
# Look for int path parameters in routes
grep -rn "user_id: int\|resource_id: int\|item_id: int" app/services/*/api/ --include="*.py"
```

**How to fix**: All API-exposed entities use UUID base classes. Path parameters accept UUID:
```python
@router.get("/users/{user_id}")
def get_user(user_id: UUID):
    return service.get_user(user_id)

# Response: {"id": "019d0a1b-7c3e-7a4f-8b5c-1234567890ab", "name": "Test User"}
```

---

## Deprecated Lifecycle Events

**Smell**: Using `@app.on_event("startup")` or `@app.on_event("shutdown")` instead of the lifespan context manager.

**What it looks like**:
```python
@app.on_event("startup")  # DEPRECATED
async def startup():
    app.state.db = await create_pool()

@app.on_event("shutdown")  # DEPRECATED
async def shutdown():
    await app.state.db.close()
```

**Why it's bad**: `on_event` is deprecated in modern FastAPI. It can't share state between startup and shutdown cleanly, and won't be supported long-term.

**How to detect**:
```bash
grep -rn "on_event\|@.*\.on_event" app/ --include="*.py"
```

**How to fix**: Use the lifespan context manager:
```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool()
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

---

## Pydantic v1 Patterns in v2 Codebase

**Smell**: Using deprecated Pydantic v1 APIs that still work but emit warnings.

**What it looks like**:
```python
class UserCreate(BaseModel):
    class Config:           # v1 style — use model_config instead
        orm_mode = True     # v1 — use from_attributes instead

    @validator("email")     # v1 — use @field_validator instead
    def check_email(cls, v): ...

user.dict()                 # v1 — use .model_dump() instead
user.json()                 # v1 — use .model_dump_json() instead
```

**How to detect**:
```bash
grep -rn "class Config:" app/ --include="*.py" | grep -v "ConfigDict"
grep -rn "orm_mode" app/ --include="*.py"
grep -rn "@validator\b\|@root_validator" app/ --include="*.py"
grep -rn "\.dict()\|\.json()" app/ --include="*.py"
```

**How to fix**:
```python
class UserCreate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str: ...

user.model_dump()
user.model_dump_json()
```

---

## Legacy Dependency Injection Style

**Smell**: Using `param = Depends(func)` instead of `Annotated[Type, Depends(func)]`.

**What it looks like**:
```python
@router.get("/users")
def list_users(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ...
```

**Why it's bad**: Mixes default values with DI. Not reusable across routes. Type checkers see the `Depends()` call as the default, not the resolved type.

**How to detect**:
```bash
grep -rn "= Depends(" app/services/*/api/ --include="*.py"
```

**How to fix**: Use `Annotated` types:
```python
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

@router.get("/users")
def list_users(db: DbSession, user: CurrentUser):
    ...
```

---

## Legacy SQLAlchemy 1.x Query Style

**Smell**: Using `session.query(Model).filter(...)` instead of SQLAlchemy 2.0 `select()` style.

**What it looks like**:
```python
users = session.query(User).filter(User.active == True).all()
```

**Why it's bad**: Legacy 1.x style. Not compatible with async sessions. Will be removed in future SQLAlchemy versions.

**How to detect**:
```bash
grep -rn "\.query(\|session\.query" app/ --include="*.py"
grep -rn "\.filter(\|\.filter_by(" app/ --include="*.py" | grep -v "# noqa"
```

**How to fix**:
```python
from sqlalchemy import select
result = session.scalars(select(User).where(User.active == True)).all()
```

---

## Unstructured Logging

**Smell**: Using bare `logging.info(f"...")` with string formatting instead of structured logging.

**What it looks like**:
```python
import logging
logger = logging.getLogger(__name__)
logger.info(f"User {user_id} created order {order_id} for ${total}")
```

**Why it's bad**: Not machine-parseable. Can't filter/aggregate in log management tools. Correlation across requests requires manual regex.

**How to detect**:
```bash
grep -rn "logging\.info\|logging\.warning\|logging\.error\|logging\.debug" app/ --include="*.py"
grep -rn "logger\.info.*f\"\|logger\.warning.*f\"\|logger\.error.*f\"" app/ --include="*.py"
```

**How to fix**: Use structlog with contextual data:
```python
import structlog
logger = structlog.get_logger()
logger.info("order_created", user_id=user_id, order_id=order_id, total=total)
```
