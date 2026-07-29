# Coding Standards — Python / FastAPI

## Language & Runtime

- Python 3.13+
- FastAPI with Pydantic v2 for validation
- SQLModel for ORM / database models
- `uv` as package manager (never `pip`)

## Type Safety

- Mandatory type hints on all function signatures, return types, and class attributes
- Use `T | None` union syntax (not `Optional[T]`)
- Use `list[int]`, `dict[str, Any]` (not `List[int]`, `Dict[str, Any]` from typing)
- No `Any` unless absolutely unavoidable — prefer `Unknown` patterns or generics
- Pydantic models for all request/response schemas (automatic validation)
- Run `mypy` (or `pyright`) on every change — type errors are blocking

## Naming Conventions

| Element       | Convention       | Example            |
| ------------- | ---------------- | ------------------ |
| Functions     | snake_case       | `get_user_by_id()` |
| Classes       | CamelCase        | `UserService`      |
| Constants     | UPPER_SNAKE_CASE | `MAX_RETRY_COUNT`  |
| Modules/files | snake_case       | `user_service.py`  |
| Env vars      | UPPER_SNAKE_CASE | `DATABASE_URL`     |

## Async Rules

- `async def` for I/O operations (HTTP calls, file I/O, message queues)
- Regular `def` for database operations with synchronous SQLModel sessions
- For async database access, use async drivers (`asyncpg`) with `AsyncSession`
- Never mix — if a function calls sync DB, it must be sync itself
- Never use `requests` in async handlers — use `httpx.AsyncClient` instead

## Import Rules

- All imports at module top level — no inline imports
- Inline imports are a design smell indicating circular dependencies
- If circular dependency exists, refactor to eliminate it (move logic to correct layer)
- Exception: test files may use inline imports for test-specific mocks only

## Code Structure

- Maximum 3 levels of nesting — extract helper functions beyond that
- Early returns: validate inputs at function start, return/raise immediately on failure
- Small functions: single responsibility, under 40 lines preferred

### Guard Clause Example

**Bad** — deeply nested:
```python
def process_order(order):
    if order:
        if order.is_valid():
            if order.has_items():
                # actual logic buried 3 levels deep
                return calculate_total(order)
    return None
```

**Good** — guard clauses:
```python
def process_order(order):
    if not order:
        return None
    if not order.is_valid():
        raise InvalidOrderError(order.id)
    if not order.has_items():
        raise EmptyOrderError(order.id)
    return calculate_total(order)
```
- Named constants: no magic numbers or strings
- Extract complex boolean conditions into named variables

## Error Handling

- All custom exceptions inherit from a base `AppError` class
- Never inherit from plain `Exception` — breaks centralized HTTP status mapping
- Use specific error subclasses: `NotFoundError`, `ConflictError`, `BadRequestError`
- Never catch generic `Exception` above `AppError` — it swallows domain errors

## Dependency Injection

Use `Annotated` types for FastAPI dependencies (PEP 593) — reusable, composable, type-checker friendly:

```python
from typing import Annotated
from fastapi import Depends

# Define reusable dependency types
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]

# Use in route handlers — clean and explicit
@router.get("/photos")
async def list_photos(db: DbSession, user: CurrentUser): ...
```

Never use the older `param: Type = Depends(func)` style — it mixes default values with DI.

## Application Lifecycle

Use the lifespan context manager for startup/shutdown — `@app.on_event()` is deprecated:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize pools, connections, caches
    app.state.db_pool = await create_pool()
    yield
    # Shutdown: clean up resources
    await app.state.db_pool.close()

app = FastAPI(lifespan=lifespan)
```

## Architecture Boundaries

- **Thin routers / fat services**: Business logic lives in the service layer, not routes
- **Repository pattern**: Services never access database sessions directly
- Services never import `Session`, `select`, or raw SQLModel queries
- Services never access `repository._session` — that is repository internals
- Clear layer boundaries: domain -> application -> infrastructure -> api

## Entity Standards

- All entities extend base classes (UUID base for API-exposed, Int base for internal)
- UUIDv7 for all entity IDs — never `uuid4()`
- No duplicate field declarations — base classes provide id, timestamps, soft-delete
- Every entity has a corresponding `Filters` Pydantic model for repository queries

## Configuration

- All behavior controlled by explicit environment variables
- Never change behavior based on `ENVIRONMENT` variable (local/test/prod)
- `ENVIRONMENT` identifies WHERE code runs, not HOW it behaves
- Use `ENABLE_X` or profile-based flags for feature toggles

## DRY Principle

- Always search before creating protocols, interfaces, or classes
- Reuse existing interfaces from the module that owns the domain
- Cross-service dependencies: import from the owning service
- One obvious way to do things — no convenience aliases or alternative formats

---

## Entity & Repository Standards

See golden-rules.md Rule 6 for the full selection matrix and decision guide.

### Entity Base Class Usage

```python
# CORRECT: Extend base class, only declare domain-specific fields
from app.core.domain.base_entity import BaseUUIDEntityWithSD

class Photo(BaseUUIDEntityWithSD, table=True):
    __tablename__ = "photos"
    # id, created_at, updated_at, deleted_at, deleted_by come from base
    title: str
    user_id: UUID = Field(foreign_key="users.id")

# WRONG: Redeclaring base fields
class Photo(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)  # Duplicate!
    created_at: datetime  # Duplicate!
```

### UUID Generation — Always UUIDv7

Always use UUIDv7 for generating new UUIDs — never `uuid4()`:

```python
from app.core.uuid_utils import generate_uuid  # Project wrapper
# OR directly:
from uuid_utils import uuid7
```

UUIDv7 benefits: time-ordered (better B-tree locality), sortable, RFC 9562 compliant.

### Repository Contracts (MANDATORY)

All repositories MUST extend `RepositoryContract[T, K, F]` from `app/core/domain/repository_contracts.py`:

```python
from app.core.domain.repository_contracts import RepositoryContract

# T = Entity type, K = ID type, F = Filters Pydantic model
class PhotoRepositoryInterface(RepositoryContract[Photo, UUID, PhotoFilters], ABC):
    # Standard methods inherited: get_by_id, get_by_ids, exists, count,
    # list_all, add, add_many, update, delete, restore, delete_hard

    @abstractmethod
    def get_by_album(self, album_id: UUID) -> list[Photo]:
        pass
```

### Entity Filters Model (MANDATORY)

Create `<Entity>Filters` Pydantic model for repository filtering:

```python
from pydantic import BaseModel

class PhotoFilters(BaseModel):
    user_id: UUID | None = None
    album_id: UUID | None = None
    is_public: bool | None = None
```

### File Locations

| Type | Location |
|------|----------|
| Interfaces | `app/services/<service>/repository_interfaces.py` (module root) |
| Implementations | `app/services/<service>/infrastructure/repositories.py` |
| Errors | `app/services/<service>/errors.py` |
| Filters | Co-located with interface or in `application/dto.py` |

---

## Cross-Service Interface Ownership

### Repository Interfaces at Module Root

Repository interfaces live at the module root in `repository_interfaces.py`. Other services import from the OWNING service — never create duplicate protocols.

### Ownership Table

| Domain | Owner Service | Interface Location |
|--------|---------------|-------------------|
| Users, Roles, RBAC | Identity | `identity/repository_interfaces.py` |
| Clients, Relationships | Clients | `clients/repository_interfaces.py` |
| Organizations | Organizations | `organizations/repository_interfaces.py` |
| Photos, Albums | Photos | `photos/repository_interfaces.py` |
| Licenses, SKUs | Licences | `licences/repository_interfaces.py` |
| Audit Logs | Audit | `audit/repository_interfaces.py` |
| Devices | Devices | `devices/repository_interfaces.py` |

### Cross-Service Access Pattern

Inject the owning module's repository interface via DI:

```python
# CORRECT: Import from owning service
from app.services.identity.repository_interfaces import RoleRepositoryInterface
from app.services.clients.repository_interfaces import ClientRelationshipRepositoryInterface

class MyService:
    def __init__(
        self,
        role_repo: RoleRepositoryInterface,
        relationship_repo: ClientRelationshipRepositoryInterface,
    ):
        self.role_repo = role_repo
        self.relationship_repo = relationship_repo

# WRONG: Creating duplicate protocol
class RoleRepositoryProtocol(Protocol):  # Already exists in Identity!
    def get_by_code(self, code: str) -> Role | None: ...

# WRONG: Adding another domain's query to your own repo
class DeviceRepository:
    def get_by_user_id(self, user_id: UUID): ...  # Users belong to Identity!

# WRONG: Duplicating logic that exists in the owning repo
class DeviceRepository:
    def reset_licenses_by_user(self, user_id: UUID): ...  # Use LicenseRepository!
```

---

## Service Isolation

See golden-rules.md Rule 8 for the full enforcement protocol.

**Quick reference**: Services NEVER import Session, select, or access repository._session. All data access goes through repository interfaces.

---

## DTO Conventions

### Naming Pattern

Use `<Action>Request` for input DTOs and `<Action>Response` for output DTOs:

```python
# CORRECT: Clear action-based naming
class CreatePhotoRequest(BaseModel):
    title: str
    album_id: UUID | None = None

class CreatePhotoResponse(BaseModel):
    id: UUID
    title: str
    created_at: datetime

class UpdatePhotoRequest(BaseModel):
    title: str | None = None

class ListPhotosResponse(BaseModel):
    items: list[PhotoSummary]
    total: int
    page: int

# WRONG: Vague or inconsistent naming
class PhotoDTO(BaseModel): ...     # Which operation?
class PhotoInput(BaseModel): ...   # Not standard
class PhotoData(BaseModel): ...    # Too generic
```

### DTOs Cross Boundaries

Only DTOs cross the API boundary — never models:

```python
# CORRECT: DTO crosses boundary
@router.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, service: UserService = Depends()):
    user = service.get_user(user_id)
    return UserResponse.model_validate(user)

# WRONG: Model crosses boundary
@router.get("/users/{user_id}", response_model=User)  # Model!
def get_user(user_id: UUID, db: Session = Depends()):
    return db.query(User).filter(User.id == user_id).first()
```

> **ADR override note**: if a project ADR in `.devt/memory/decisions/` contradicts these standards, the ADR wins. ADRs are constitutional. Run `node bin/devt-tools.cjs memory list decision` to see what's binding.
