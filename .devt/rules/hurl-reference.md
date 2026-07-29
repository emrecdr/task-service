# HURL E2E Test Reference

> **Reference file for `testing-patterns` skill.** See [SKILL.md](SKILL.md) for quick start.

This guide covers HURL E2E test organization, structure, and best practices.

## Contents

- [Directory Structure](#directory-structure)
- [MANDATORY: Use the Official Template](#mandatory-use-the-official-template)
- [Metadata Requirements](#metadata-requirements-dashboard-validation)
- [File Naming Convention](#file-naming-convention)
- [Request Structure](#request-structure)
- [Variable Capture Pattern](#variable-capture-pattern)
- [Email Token Handling](#email-token-handling-async-flows)
- [SMS Token Handling](#sms-token-handling-2fa-flows)
- [Assertions](#assertions)
- [Test Data Management](#test-data-management)
- [Running Tests](#running-tests)
- [Debugging Tips](#debugging-tips)

---

## Directory Structure

```
tests/hurl/
├── .env.hurl               # Hurl test variables (NOT a .env.* file)
├── TEMPLATE.hurl.example   # MANDATORY template for new tests
├── {letter}{nn}_{name}.hurl # Domain-prefixed test files (e.g., c01_client_relationships.hurl)
├── metadata.json           # Execution order + phase labels (EDIT THIS when adding tests)
├── README.md               # E2E testing guide
└── scripts/                # Runner scripts
    └── validate_hurl.sh    # Validate files for dashboard compatibility
```

---

## MANDATORY: Use the Official Template

**Always copy the template when creating new Hurl test files:**

```bash
cp tests/hurl/TEMPLATE.hurl.example tests/hurl/{letter}{nn}_{feature_name}.hurl
```

**Template location:** `tests/hurl/TEMPLATE.hurl.example`

The template provides:
- File header with overview, prerequisites, output captures
- **Metadata format guide** - Required `Actor:` and `Expected:` fields
- Phase-based organization (CRUD -> Error Cases -> Cleanup)
- Example tests for all HTTP status codes
- Summary section for documentation

---

## Metadata Requirements (Dashboard Validation)

Every HTTP request MUST have metadata comments for the Hurl Dashboard:

```hurl
# REQUIRED fields (validation errors if missing):
# @ACTOR: System Admin (SYSTEM:MANAGE permission)
# @EXPECTED: 201 Created with resource UUID
# @CONTEXT: Creating a new resource for testing

# RECOMMENDED field (validation warnings if missing):
# @WHY: Resources must exist before assignment

# OPTIONAL fields (for context):
# @CAPTURES: resource_uuid
```

### Validation Script

**⚠️ AUTOMATIC EXECUTION REQUIRED:** Validate HURL files automatically - NEVER ask user:

```bash
# Validate single file (run automatically, don't ask)
./tests/hurl/scripts/validate_hurl.sh tests/hurl/filename.hurl

# Strict mode (fail on warnings)
./tests/hurl/scripts/validate_hurl.sh --strict tests/hurl/filename.hurl

# Quiet mode (errors only)
./tests/hurl/scripts/validate_hurl.sh --quiet tests/hurl/filename.hurl
```

**Exit codes:** 0=passed, 1=errors found, 2=usage error

**Anti-Pattern:** ❌ NEVER ask user "Would you like me to run validation?" - Just run it.

**Anti-Pattern:** ❌ NO temporal markers (`(NEW)`, `(UPDATED)`, `(FIXED)`) or superlatives (`enhanced`, `improved`, `optimized`) in test descriptions, phase names, or comments. Describe what exists, not when it was added.

### Required Tags

| Tag | Required | Description |
|-----|----------|-------------|
| `@ACTOR:` | ✅ Yes | Who performs the action |
| `@EXPECTED:` | ✅ Yes | Expected HTTP status/outcome |
| `@CONTEXT:` | ✅ Yes | What this test is about |
| `@WHY:` | Recommended | Business reason (warns if missing) |
| `@CAPTURES:` | Optional | Variables captured |

### Actor Field Format

```hurl
# @ACTOR: <Role> (<Scope>:<Permission> permission)
# Examples:
# @ACTOR: System Admin (SYSTEM:MANAGE permission)
# @ACTOR: Organization Admin (ORGANIZATION:MANAGE permission)
# @ACTOR: Caregiver (RELATIVE:VIEW permission)
# @ACTOR: Anonymous (No authentication)
```

### Expected Field Format

```hurl
# @EXPECTED: <HTTP Status> <Description>
# Examples:
# @EXPECTED: 200 OK with list of resources
# @EXPECTED: 201 Created with resource UUID
# @EXPECTED: 204 No Content
# @EXPECTED: 401 Unauthorized - invalid token
# @EXPECTED: 403 Forbidden - insufficient permissions
# @EXPECTED: 404 Not Found - resource doesn't exist
# @EXPECTED: 422 Validation Error - missing required field
```

---

## File Naming Convention

**Pattern:** `{letter}{nn}_{name}.hurl` (domain-prefixed naming)

- **Letter** (a-s) = domain group — instantly identifies what service/area the test covers
- **Number** (01-99) = order within domain — tens digit groups related sub-topics
- **Name** = descriptive snake_case name

```
tests/hurl/
├── a01_health_probes.hurl           # a = Infrastructure
├── b01_auth_setup.hurl              # b = Auth & Identity
├── c01_client_relationships.hurl    # c = Clients
├── d01_licenses.hurl                # d = Licenses
├── e01_user_api.hurl                # e = User Profile
├── f01_2fa_email.hurl               # f = Two-Factor Auth
├── g01_rbac_advanced.hurl           # g = RBAC & Permissions
├── h01_organization_users.hurl      # h = Organizations
├── j01_photo_albums.hurl            # j = Photos
├── k01_agenda.hurl                  # k = Agenda
├── l01_devices.hurl                 # l = Devices
├── m01_app_versions.hurl            # m = Tablet Communication
├── n01_video_calling.hurl           # n = Communication
├── o01_invoices.hurl                # o = Billing
├── p01_dashboard.hurl               # p = Dashboards
├── q01_countries.hurl               # q = Cross-Cutting
├── r01_token_single_use.hurl        # r = Security
├── s01_family_journey.hurl          # s = Integration Journeys
```

> **Note**: Letter `i` is skipped to avoid confusion with `1` in monospace fonts.

### Execution Order

Files execute in `metadata.json` array order (not filename order). A foundation chain of 7 files must run first: `b01→c01→c02→c03→c10→d01→g01`. See `tests/hurl/README.md` for full execution order documentation.

---

## Required Test Cases per Endpoint

Every HURL test file MUST include:

| Case Type | HTTP Status | Description |
|-----------|-------------|-------------|
| Success | 200/201/204 | Valid request with expected response |
| Validation Error | 422 | Invalid input (missing fields, wrong types) |
| Auth Error | 401 | Missing or invalid token |
| Permission Error | 403 | Valid token but insufficient permissions |
| Not Found | 404 | Resource doesn't exist (for GET/PUT/DELETE) |

### Example Test Structure

```hurl
# ============================================================
# TEST: Create Resource - Success
# ============================================================
# Actor: System Admin (SYSTEM:MANAGE permission)
# Expected: 201 Created with resource UUID

POST {{base_url}}/api/v1/resources
Authorization: Bearer {{admin_token}}
Content-Type: application/json
{
    "name": "Test Resource",
    "description": "Test description"
}

HTTP 201
[Captures]
resource_uuid: jsonpath "$.id"

[Asserts]
jsonpath "$.name" == "Test Resource"


# ============================================================
# TEST: Create Resource - Validation Error (missing name)
# ============================================================
# Actor: System Admin (SYSTEM:MANAGE permission)
# Expected: 422 Validation Error - missing required field

POST {{base_url}}/api/v1/resources
Authorization: Bearer {{admin_token}}
Content-Type: application/json
{
    "description": "Missing name field"
}

HTTP 422
[Asserts]
jsonpath "$.detail[0].loc[1]" == "name"


# ============================================================
# TEST: Create Resource - Unauthorized
# ============================================================
# Actor: Anonymous (No authentication)
# Expected: 401 Unauthorized - missing token

POST {{base_url}}/api/v1/resources
Content-Type: application/json
{
    "name": "Test Resource"
}

HTTP 401


# ============================================================
# TEST: Get Resource - Not Found
# ============================================================
# Actor: System Admin (SYSTEM:MANAGE permission)
# Expected: 404 Not Found - resource doesn't exist

GET {{base_url}}/api/v1/resources/00000000-0000-0000-0000-000000000000
Authorization: Bearer {{admin_token}}

HTTP 404
```

---

## Running HURL Tests

```bash
# All E2E tests
make test-hurl

# Infrastructure tests only (health, diagnostics)
make test-hurl-infra

# All Hurl tests (infra + main)
make test-hurl-all

# Verbose with phase descriptions
make test-hurl-verbose

# With dashboard UI
make test-hurl-dashboard
```

### Timeout and Error Handling

**Timeout**: Default 10 minutes (600s). Full suite typically runs in ~8 minutes.

**Exit Codes and Diagnostics**:
| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | All tests passed |
| 124 | Timeout | Check server responsiveness, database queries |
| 2 | Parse Error | Fix HURL syntax |
| 3 | Runtime Error | Verify server running, check connections |
| 4 | Assertion Failure | Review JSON details in output |

The runner provides contextual diagnostics for each failure type.

### Environment Variables

HURL tests use variables from `.env.hurl`:

```bash
# .env.hurl example
base_url=http://localhost:8000
admin_token=<system_admin_token>
org_admin_token=<org_admin_token>
```

---

## Phase-Based Organization

Organize tests in logical phases:

```hurl
# ============================================================
# PHASE 1: Setup - Create dependencies
# ============================================================
# Create user, organization, etc. needed for subsequent tests

# ============================================================
# PHASE 2: CRUD Operations
# ============================================================
# Create, Read, Update, Delete tests

# ============================================================
# PHASE 3: Error Cases
# ============================================================
# 401, 403, 404, 422 error scenarios

# ============================================================
# PHASE 4: Cleanup
# ============================================================
# Delete created resources in reverse order
```

---

## Common Assertions

```hurl
# Status code
HTTP 200
HTTP 201
HTTP 204

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
header "X-Request-ID" exists

# Body assertions
body contains "success"
```

---

## Captures for Chaining Tests

```hurl
# Capture UUID from creation response
POST {{base_url}}/api/v1/users
...
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

---

## Email Token Handling (Async Flows)

Some tests require tokens from async email operations (verification, password reset). The framework handles this automatically.

### How It Works

1. Server sends email via `MemoryEmailBackend` → tokens stored in-memory
2. Subsequent test queries `/api/v1/testing/email-tokens/{email}` with retry polling
3. Token captured as variable for use in subsequent requests

### Split File Pattern

Email flows are split into two files for token injection:

| Setup File | Completion File | Token Variable |
|------------|-----------------|----------------|
| `b01_auth_setup.hurl` | `b10_email_verification.hurl` | `email_verification_token` |
| `e20_password_session.hurl` | `e21_password_reset.hurl` | `password_reset_token` |

**Usage in completion file:**
```hurl
# Token is auto-injected from email mock file
GET {{base_url}}/api/v1/auth/verify-email/{{email_verification_token}}
Accept: application/json

HTTP 200
```

---

## SMS Token Handling (2FA Flows)

SMS 2FA tests require verification codes from async SMS operations. The framework handles this automatically.

### How It Works

1. Server sends SMS via `MemorySMSBackend` → code stored in-memory
2. Subsequent test queries `/api/v1/testing/sms-code/{phone}` with retry polling
3. 6-digit code captured as `sms_2fa_code` variable

### SMS JSON Format

```json
{
    "to": "+31612345678",
    "message": "Your BBrain verification code is: 123456",
    "timestamp": "2025-01-19T12:00:00Z"
}
```

### Configuration (.env.test)

```bash
EMAIL_BACKEND=["memory"]   # Required for email token capture
SMS_BACKEND=["memory"]     # Required for SMS code capture
SMS_2FA_ENABLED=true       # Enable SMS 2FA feature
PUSH_BACKEND=["memory"]    # Required for push notification assertions
```

### Usage in Test Files

```hurl
# Request 2FA code via SMS (triggers SMS file write)
POST {{base_url}}/api/v1/auth/2fa/enable
Authorization: Bearer {{user_token}}
Content-Type: application/json
{
    "delivery_method": "sms"
}

HTTP 200

# Code is auto-injected from SMS mock file
POST {{base_url}}/api/v1/auth/2fa/verify
Content-Type: application/json
{
    "partial_token": "{{sms_2fa_partial_token}}",
    "code": "{{sms_2fa_code}}"
}

HTTP 200
```

### SMS Test Files (Split Pattern)

SMS 2FA uses a two-file split pattern for code injection:

| File | Tests | Coverage |
|------|-------|----------|
| `f10_2fa_sms.hurl` | SMS 2FA setup | Setup, enable, SMS unavailable (no phone), error cases, final challenge |
| `f11_2fa_sms_verification.hurl` | SMS 2FA completion | Code verification (SUCCESS), invalidation, cleanup (both users) |

**Why split?** The first file triggers the SMS code, the second uses it:
1. `f10_2fa_sms.hurl` triggers final challenge → SMS code captured via testing endpoint
2. `f11_2fa_sms_verification.hurl` uses captured `{{sms_2fa_code}}` to complete verification

---

## Validation Checklist

Before marking HURL tests complete:

- [ ] Used official template (`TEMPLATE.hurl.example`)
- [ ] All requests have required metadata (`@ACTOR:`, `@EXPECTED:`, `@CONTEXT:`)
- [ ] All requests have recommended metadata (`@WHY:`)
- [ ] **⚠️ Validation passed (AUTOMATIC):** `./tests/hurl/scripts/validate_hurl.sh <file>` - Run automatically, NEVER ask user
- [ ] Success case (200/201/204) tested
- [ ] Validation error (422) tested
- [ ] Auth error (401) tested
- [ ] Permission error (403) tested
- [ ] Not found (404) tested (for GET/PUT/DELETE)
- [ ] File follows domain-prefixed naming convention (`{letter}{nn}_{name}.hurl`)
- [ ] Registered in `metadata.json` (filename, phase_label, module)
- [ ] `.hurl` file has required headers (`@NAME`, `@DESCRIPTION`, `@MODULE`, `@TAGS`, `@COVERS`)
- [ ] Tests run successfully with `make test-hurl`
- [ ] **Validation results included in handoff** (code-reviewer will REJECT without this)
