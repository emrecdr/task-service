# Pytest Reference

> **Reference file for `testing-patterns` skill.** See [SKILL.md](SKILL.md) for quick start.

This guide covers pytest patterns, mocking strategy, fixtures, and integration testing.

## Contents

- [Mocking Strategy](#mocking-strategy)
- [Mock External Services](#mock-external-services)
- [Fixtures](#fixtures)
- [Test Organization](#test-organization)
- [Integration Tests](#integration-tests)
- [Async Testing](#async-testing)
- [Coverage Requirements](#coverage-requirements)
- [Common Patterns](#common-patterns)
- [Anti-Patterns to Avoid](#anti-patterns-to-avoid)

---

## Mocking Strategy

### Minimal Mocking Philosophy

**CRITICAL: Maximum 3 mocks per test.** If more mocks are needed:

- The code may have too many dependencies -> refactor
- The test should be an integration test instead

### Acceptable Mocking Targets

**Preferred to Mock:**
- External HTTP clients (Pushy, SendGrid, Twilio, WooCommerce)
- Time/date functions (`datetime.now()`, `time.time()`)
- Random generators (`uuid.uuid4()`)
- File system operations (when testing business logic)

**Avoid Mocking (but OK if truly needed):**
- Database repositories (prefer integration tests)
- Internal services (may indicate tight coupling)
- Domain logic (usually better tested directly)

**Hard Limit:**
- More than 3 mocks in a single test -> use integration test instead

---

## Mock External Services

**Always mock external APIs** (Pushy, Twilio, SendGrid, WooCommerce):

```python
import pytest
from unittest.mock import Mock, AsyncMock

@pytest.fixture
def mock_sendgrid():
    """Mock SendGrid external service."""
    mock = AsyncMock()
    mock.send_email.return_value = {"success": True, "message_id": "msg_123"}
    return mock

def test_send_verification_email(mock_sendgrid):
    """Test email sending with mocked SendGrid (1 mock only)."""
    service = NotificationService(sendgrid=mock_sendgrid)
    result = await service.send_verification_email("test@example.com")

    assert result["success"] is True
    mock_sendgrid.send_email.assert_called_once()
```

---

## Database Testing Strategy

**DO NOT mock repositories for unit tests.** Use these approaches instead:

```python
# CORRECT: Test business logic without database
def test_license_expiry_calculation():
    """Test pure business logic - no mocking needed."""
    license = License(
        created_at=datetime(2024, 1, 1),
        duration_days=365
    )
    expiry = calculate_license_expiry(license)
    assert expiry == datetime(2025, 1, 1).date()

# CORRECT: Use integration test for repository operations
@pytest.mark.integration
async def test_user_repository_creates_user(db_session):
    """Integration test with real database."""
    repo = UserRepository(db_session)
    user = await repo.create(email="test@example.com", name="Test")
    assert user.id is not None

# WRONG: Mocking repositories in unit tests
def test_with_mocked_repository(mock_user_repo):
    """This should be an integration test instead."""
    pass  # Don't do this
```

---

## Mock FastAPI Dependencies

```python
from fastapi.testclient import TestClient
from app.main import app

def test_login_endpoint():
    """Test login endpoint with mocked dependencies."""
    # Override dependency
    def mock_get_service():
        mock_service = Mock()
        mock_service.login.return_value = LoginResponse(
            access_token="test_token",
            user_id=1
        )
        return mock_service

    app.dependency_overrides[get_identity_service] = mock_get_service

    client = TestClient(app)
    response = client.post("/api/v1/identity/login", json={
        "email": "test@example.com",
        "password": "password"
    })

    assert response.status_code == 200
    assert response.json()["access_token"] == "test_token"
```

---

## Fixture Patterns

### Common Fixtures

```python
import pytest
from unittest.mock import Mock, MagicMock
from sqlmodel import Session

@pytest.fixture
def mock_db_session():
    """Mock database session for testing."""
    session = Mock(spec=Session)
    session.add = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    session.execute = Mock()
    return session

@pytest.fixture
def mock_user_repo():
    """Mock UserRepository with common methods."""
    repo = Mock()
    repo.get_by_id = Mock(return_value=None)
    repo.get_by_email = Mock(return_value=None)
    repo.create = Mock()
    repo.update = Mock()
    repo.delete = Mock()
    return repo

@pytest.fixture
def sample_user():
    """Sample user object for testing."""
    user = Mock()
    user.id = 1
    user.email = "test@example.com"
    user.name = "Test User"
    user.hashed_password = "$2b$12$..."
    user.is_active = True
    return user

@pytest.fixture
def sample_login_request():
    """Sample login request DTO."""
    from app.services.identity.application.dto import LoginRequest
    return LoginRequest(
        email="test@example.com",
        password="password123"
    )
```

### Fixture Scope

```python
@pytest.fixture(scope="function")  # Default - new instance per test
def mock_service():
    return Mock()

@pytest.fixture(scope="module")  # One instance per test module
def app_config():
    return {"database_url": "sqlite:///:memory:"}

@pytest.fixture(scope="session")  # One instance per test session
def test_db_engine():
    engine = create_engine("sqlite:///:memory:")
    yield engine
    engine.dispose()
```

---

## Example Test Suite

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock

class TestUserLogin:
    """Test suite for user login endpoint."""

    def test_login_success(self, mock_user_service):
        """Happy path: successful login with valid credentials."""
        mock_user_service.login.return_value = LoginResponse(
            access_token="valid_token",
            refresh_token="refresh_token",
            user_id=1,
            expires_in=604800
        )

        client = TestClient(app)
        response = client.post("/api/v1/identity/login", json={
            "email": "user@example.com",
            "password": "securepass123"
        })

        assert response.status_code == 200
        assert "access_token" in response.json()
        assert response.json()["user_id"] == 1

    def test_login_invalid_credentials(self, mock_user_service):
        """Validation error: invalid email or password."""
        mock_user_service.login.side_effect = InvalidCredentialsError()

        client = TestClient(app)
        response = client.post("/api/v1/identity/login", json={
            "email": "user@example.com",
            "password": "wrongpassword"
        })

        assert response.status_code == 401
        assert "Invalid credentials" in response.json()["detail"]

    def test_login_missing_fields(self):
        """Validation error: missing required fields."""
        client = TestClient(app)
        response = client.post("/api/v1/identity/login", json={
            "email": "user@example.com"
            # Missing password field
        })

        assert response.status_code == 422
        assert "field required" in response.json()["detail"][0]["msg"]
```

---

## Integration Testing

### When to Use Integration Tests

Use integration tests when:
- Testing complex database queries
- Testing transaction behavior
- Testing multiple services interacting
- Testing background tasks with real task queue

### Integration Test Setup

```python
import pytest
from sqlmodel import create_engine, Session, SQLModel
from app.services.identity.infrastructure.models import User

@pytest.fixture(scope="module")
def test_engine():
    """Create test database engine."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()

@pytest.fixture
def test_db(test_engine):
    """Create test database session."""
    with Session(test_engine) as session:
        yield session
        session.rollback()

@pytest.mark.integration
def test_create_user_integration(test_db):
    """Integration test with real database."""
    # Create user
    user = User(
        email="integration@example.com",
        hashed_password="hashed",
        name="Integration Test"
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)

    # Verify user created
    assert user.id is not None

    # Query user using select statement
    from sqlmodel import select
    statement = select(User).where(User.email == "integration@example.com")
    result = test_db.scalars(statement).first()

    assert result is not None
    assert result.email == "integration@example.com"
```

### Docker Integration Tests

For full integration tests with PostgreSQL:

```bash
# Start PostgreSQL in Docker
make compose-up

# Run integration tests
DATABASE_URL="postgresql+psycopg://gfapi_user:gfapi_password@localhost:5432/gfapi_db" \
  pytest app/services/<service>/tests -m integration -v

# OR use make command
make test-integration-full
```

---

## Test Coverage

### Run Coverage Report

```bash
# Run tests with coverage
pytest app/services/<service>/tests \
  --cov=app/services/<service> \
  --cov-report=term \
  --cov-report=html

# View HTML report
open htmlcov/index.html
```

### Coverage Target

- **Minimum:** 70% coverage on critical paths
- **Focus on:** Service layer business logic, repository operations
- **Don't stress over:** DTOs (Pydantic validates automatically), simple getters/setters

---

## Test Organization

### File Structure

```
app/services/<service>/tests/
├── __init__.py
├── conftest.py              # Shared fixtures
├── test_<endpoint_slug>.py  # Endpoint-specific tests
├── test_service.py          # Service layer tests
├── test_repositories.py     # Repository tests
└── integration/
    ├── __init__.py
    └── test_<feature>_integration.py
```

### conftest.py Example

```python
"""Shared test fixtures for identity service."""
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_db_session():
    """Mock database session."""
    return Mock()

@pytest.fixture
def mock_user_repo():
    """Mock user repository."""
    repo = Mock()
    repo.get_by_email = Mock(return_value=None)
    return repo

@pytest.fixture
def sample_user():
    """Sample user for testing."""
    user = Mock()
    user.id = 1
    user.email = "test@example.com"
    return user
```

---

## Running Tests

```bash
# Run all tests
pytest app/services/<service>/tests -v

# Run specific test file
pytest app/services/identity/tests/test_login.py -v

# Run specific test function
pytest app/services/identity/tests/test_login.py::test_login_success -v

# Run tests by marker
pytest -m integration -v      # Only integration tests
pytest -m "not integration" -v  # Skip integration tests

# Run with coverage
pytest app/services/<service>/tests \
  --cov=app/services/<service> \
  --cov-report=term-missing \
  -v
```

---

## Common Pitfalls

| Pitfall | Problem | Solution |
|---------|---------|----------|
| Testing every edge case | Pydantic already validates | Test main features only |
| Real database in unit tests | Slow, requires setup | Mock or use integration test |
| Not asserting mock calls | Don't know if mock was called | `assert_called_once_with()` |
| Too many mocks (>3) | Test is too complex | Use integration test instead |
| Mocking repositories | Fragile, doesn't test real behavior | Integration test with real DB |

### Examples

```python
# WRONG: Not asserting mock calls
def test_send_email(mock_sendgrid):
    service.send_email("test@example.com")
    # Missing assertion - did mock get called?

# CORRECT: Assert mock interactions
def test_send_email(mock_sendgrid):
    service.send_email("test@example.com")
    mock_sendgrid.send.assert_called_once_with("test@example.com")
```

---

## Validation Checklist

Before marking pytest tests complete:

- [ ] Unit tests use minimal mocking (<=3 mocks per test)
- [ ] External services mocked (SendGrid, Twilio, Pushy)
- [ ] Repositories NOT mocked (use integration tests)
- [ ] Mock assertions verify interactions
- [ ] Coverage >= 70% on critical paths
- [ ] All tests pass (`make test-unit`)
- [ ] Test names clearly describe what's being tested
