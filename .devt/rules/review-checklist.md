# Review Checklist — Python / FastAPI

Language-specific review priorities. The code-reviewer reads this alongside `coding-standards.md`.

---

## CRITICAL — Security

- [ ] **SQL injection**: f-strings or `.format()` in queries — use parameterized queries or ORM methods
- [ ] **Command injection**: unvalidated input in `subprocess` — use list args, never `shell=True` with user input
- [ ] **Path traversal**: user-controlled paths without `os.path.normpath` + prefix check
- [ ] **Eval/exec**: dynamic code execution with untrusted input
- [ ] **Unsafe deserialization**: use safe loaders only, never load untrusted binary formats
- [ ] **Hardcoded secrets**: API keys, passwords, tokens in source — use environment variables
- [ ] **Weak crypto**: MD5/SHA1 for security purposes — use SHA-256+ or bcrypt for passwords
- [ ] **CORS misconfiguration**: `allow_origins=["*"]` in production

## CRITICAL — Error Handling

- [ ] **Bare except**: `except: pass` — always catch specific exceptions
- [ ] **Swallowed exceptions**: silent `except` without logging — at minimum `logger.exception()`
- [ ] **Missing context managers**: manual file/resource management — use `with` statements
- [ ] **Async exception loss**: `asyncio.create_task()` without error handling

## HIGH — Type Safety

- [ ] Public functions missing type annotations (parameters + return type)
- [ ] Using `Any` when a specific type is possible
- [ ] Missing `T | None` for nullable parameters (not bare `None` default without type)
- [ ] Pydantic models missing field validators for business rules

## HIGH — Pythonic Patterns

- [ ] List comprehension preferred over C-style loop with `.append()`
- [ ] `isinstance()` not `type() ==` for type checks
- [ ] `Enum` not magic numbers/strings for fixed values
- [ ] `"".join()` not string concatenation in loops
- [ ] **Mutable default arguments**: `def f(x=[])` — use `def f(x=None)`
- [ ] `value is None` not `value == None`
- [ ] Not shadowing builtins (`list`, `dict`, `str`, `id`, `type`)

## HIGH — Concurrency & Performance

- [ ] Shared mutable state without locks — use `threading.Lock` or `asyncio.Lock`
- [ ] Blocking calls (`time.sleep`, `requests.get`) in async handlers — use async equivalents
- [ ] N+1 queries in loops — batch with `selectinload` or bulk operations
- [ ] Missing eager loading for related objects accessed in response
- [ ] Sync I/O in async path — use `run_in_executor` or async libraries

## HIGH — FastAPI Specific

- [ ] Missing `response_model` on endpoints — response shape is undocumented
- [ ] Missing Pydantic validation on request bodies — raw dicts from untrusted input
- [ ] `HTTPException` without appropriate status codes
- [ ] Missing dependency injection — hardcoded service instantiation
- [ ] Background tasks without error handling
- [ ] Missing lifespan handler for startup/shutdown resources

## MEDIUM — Code Quality

- [ ] Functions over 50 lines — extract helper
- [ ] Functions with more than 5 parameters — use dataclass/model
- [ ] Deep nesting (> 4 levels) — use early returns
- [ ] Duplicate code patterns — extract shared function
- [ ] Magic numbers without named constants
- [ ] `print()` instead of `logging` / `structlog`
- [ ] `from module import *` — namespace pollution

## MEDIUM — Testing Gaps

- [ ] New endpoint without corresponding test
- [ ] Error paths not tested (4xx, 5xx responses)
- [ ] Mock overuse — prefer integration tests with real DB where feasible
- [ ] Missing edge case tests for boundary values

## Diagnostic Commands

```bash
ruff check .                               # Fast linting
pyright                                    # Type checking
bandit -r .                                # Security scan
pytest --cov=app --cov-report=term-missing # Test coverage
```

## Approval Criteria

- **Approve**: No CRITICAL or HIGH issues
- **Request changes**: Any CRITICAL or HIGH issue found
- **Note**: MEDIUM issues are advisory — mention but don't block

> **ADR/REJ alignment**: before approving a change, confirm: (a) no governing ADR is silently violated; (b) no proposed approach matches a REJ tombstone in `.devt/memory/rejected/`. The Pre-Flight Brief surfaces both.
