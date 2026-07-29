# Hurl Test Coverage Checklist Template

## Purpose

This template ensures **comprehensive Hurl test coverage** for every API endpoint. Tester agent MUST complete this checklist BEFORE writing tests.

## How to Use

1. **Copy this template** for each endpoint being tested
2. **Fill in all sections** by inspecting the actual FastAPI endpoint signature
3. **Create one test per checkbox** item
4. **Verify all boxes checked** before marking testing complete

---

## Endpoint Information

```yaml
endpoint:
  method: GET | POST | PUT | PATCH | DELETE
  path: /api/v1/...
  file: app/services/<service>/api/v1/<routes_file>.py
  line: <line_number>
  permission: <scope>:<action>  # e.g., SYSTEM:READ, ORGANIZATION:WRITE
```

---

## Step 1: Analyze Endpoint Signature (MANDATORY)

**Read the actual endpoint function** and extract:

### Path Parameters
```python
# Example: GET /api/v1/users/{user_id}/photos/{photo_id}
path_params:
  - name: user_id
    type: UUID
    required: true
  - name: photo_id
    type: UUID
    required: true
```

### Query Parameters (ALL MUST BE TESTED)
```python
# Example: GET /api/v1/admin/call-logs?sender_id=...&receiver_id=...&license_id=...
query_params:
  - name: page
    type: int
    default: 1
    constraints: ge=1
  - name: page_size
    type: int
    default: 20
    constraints: ge=1, le=200
  - name: sender_id
    type: UUID | None
    default: None
  - name: receiver_id
    type: UUID | None
    default: None
  - name: license_id
    type: UUID | None
    default: None
  - name: date_from
    type: str | None
    default: None
    format: ISO 8601
  - name: date_to
    type: str | None
    default: None
    format: ISO 8601
  - name: call_type
    type: str | None
    default: None
    allowed: video, audio
```

### Request Body Fields (for POST/PUT/PATCH)
```python
body_fields:
  - name: title
    type: str
    required: true
    constraints: min_length=1, max_length=255
  - name: description
    type: str | None
    required: false
```

---

## Step 2: Test Case Enumeration (MANDATORY)

### A. Success Cases (HTTP 200/201/204)

| # | Test Case | Query/Body | Expected |
|---|-----------|------------|----------|
| [ ] | Default request (no params) | - | 200 OK with defaults |
| [ ] | With pagination (page=1, page_size=5) | page=1&page_size=5 | 200, respects pagination |
| [ ] | With page 2 | page=2&page_size=5 | 200, offset correct |

**For each query parameter, add:**
| [ ] | Filter by {param_name} | {param_name}={valid_value} | 200 OK, filter applied |

**For LIST endpoints with filters:**
| [ ] | Combined filters | param1=x&param2=y&page=1 | 200 OK, all filters applied |

### B. Validation Errors (HTTP 422)

| # | Test Case | Invalid Input | Expected Error |
|---|-----------|---------------|----------------|
| [ ] | page_size exceeds max | page_size=500 | 422, detail shows limit |
| [ ] | page < 1 | page=0 | 422, must be >= 1 |
| [ ] | Invalid UUID format | sender_id=not-a-uuid | 422, invalid UUID |
| [ ] | Invalid enum value | call_type=invalid | 422, not in allowed |
| [ ] | Invalid date format | date_from=not-a-date | 422, invalid format |

**For POST/PUT/PATCH with body:**
| [ ] | Missing required field | {body without required} | 422, field required |
| [ ] | Invalid field type | {"field": wrong_type} | 422, type error |

### C. Authentication Errors (HTTP 401)

| # | Test Case | Auth Header | Expected |
|---|-----------|-------------|----------|
| [ ] | No auth header | (none) | 401 Unauthorized |
| [ ] | Invalid token format | Bearer invalid | 401 Unauthorized |

### D. Authorization Errors (HTTP 403)

| # | Test Case | Actor | Expected |
|---|-----------|-------|----------|
| [ ] | Wrong scope | ORGANIZATION token on SYSTEM endpoint | 403 Forbidden |
| [ ] | Insufficient permission | READ-only on WRITE endpoint | 403 Forbidden |

### E. Not Found Errors (HTTP 404) - For endpoints with path params

| # | Test Case | Path Param | Expected |
|---|-----------|------------|----------|
| [ ] | Resource not found | {id}=non-existent-uuid | 404 Not Found |

### F. Conflict Errors (HTTP 409) - For create/update endpoints

| # | Test Case | Scenario | Expected |
|---|-----------|----------|----------|
| [ ] | Duplicate resource | Create existing | 409 Conflict |

---

## Step 3: Test Count Summary

Before writing tests, count expected tests:

```yaml
test_counts:
  success_cases: X
  validation_errors: X
  auth_errors: 2  # Always 2: no token, invalid token
  permission_errors: X  # Based on permission requirements
  not_found_errors: X  # Based on path params
  conflict_errors: X  # Based on uniqueness constraints
  total: X
```

---

## Step 4: Endpoint-Type Specific Requirements

### LIST Endpoints (GET returning Page[T])

**MANDATORY tests for ALL list endpoints:**

- [ ] Default pagination (page=1, default page_size)
- [ ] Custom pagination (page=1, page_size=5)
- [ ] Page 2 (validates offset calculation)
- [ ] page_size max limit exceeded (422)
- [ ] **EACH query filter parameter tested individually**
- [ ] Combined filters (at least 2 filters together)
- [ ] Empty results (valid query, 0 matches) - should return 200, not 404

### GET Single Resource Endpoints

**MANDATORY tests:**

- [ ] Resource exists (200)
- [ ] Resource not found (404)
- [ ] Invalid ID format (422)

### CREATE Endpoints (POST)

**MANDATORY tests:**

- [ ] Valid creation (201)
- [ ] Missing required fields (422)
- [ ] Invalid field types (422)
- [ ] Duplicate/conflict (409 if applicable)

### UPDATE Endpoints (PUT/PATCH)

**MANDATORY tests:**

- [ ] Valid update (200)
- [ ] Resource not found (404)
- [ ] Invalid fields (422)
- [ ] Optimistic locking conflict (409 if applicable)

### DELETE Endpoints

**MANDATORY tests:**

- [ ] Valid deletion (204)
- [ ] Resource not found (404)
- [ ] Protected resource (409 or 400 if applicable)

---

## Step 5: Verification Before Handoff

**Tester MUST verify:**

- [ ] All query parameters from endpoint signature have tests
- [ ] All constraint boundaries tested (min, max, allowed values)
- [ ] Auth tests (401) present
- [ ] Permission tests (403) present if scope-restricted
- [ ] Test file registered in `metadata.json` (filename, phase_label, module)
- [ ] Validation passes: `bash tests/hurl/scripts/validate_hurl.sh tests/hurl/<file>.hurl`
- [ ] All tests pass: `make hurl-test`

---

## Example: Call Log Admin Endpoint

```yaml
endpoint:
  method: GET
  path: /api/v1/admin/call-logs
  permission: SYSTEM:READ

query_params:
  - page (int, default=1, ge=1)
  - page_size (int, default=20, ge=1, le=200)
  - sender_id (UUID | None)
  - receiver_id (UUID | None)
  - license_id (UUID | None)
  - date_from (str | None, ISO 8601)
  - date_to (str | None, ISO 8601)
  - call_type (str | None, "video" | "audio")

required_tests:
  success:
    - [ ] Default pagination
    - [ ] Custom pagination (page=1, page_size=5)
    - [ ] Page 2
    - [ ] Filter by sender_id
    - [ ] Filter by receiver_id
    - [ ] Filter by license_id
    - [ ] Filter by date_from/date_to
    - [ ] Filter by call_type
    - [ ] Combined filters
  validation:
    - [ ] page_size > 200 (422)
    - [ ] Invalid UUID for sender_id (422)
  auth:
    - [ ] No token (401)
  permission:
    - [ ] ORGANIZATION token (403)

total_tests: 12
```
