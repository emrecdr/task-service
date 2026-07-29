# Hurl Test Registration Reference

> Reference for the tester agent. See `testing-patterns.md` for overview.

## Contents

- [Overview](#overview)
- [Registration Steps](#registration-steps)
  - [Step 1: Create the test file](#step-1-create-the-test-file)
  - [Step 2: Validate the file](#step-2-validate-the-file)
  - [Step 3: Add to metadata.json](#step-3-add-to-metadatajson)
  - [Step 4: Verify registration](#step-4-verify-registration)
- [Execution Order Rules](#execution-order-rules)
- [Anti-Patterns](#anti-patterns)

---

## Overview

When creating a new `.hurl` file, register it in **ONE file**: `tests/hurl/metadata.json`

Array position = execution order. No other files need editing.

---

## Registration Steps

### Step 1: Create the test file

Use the domain-prefixed naming scheme: `{letter}{nn}_{name}.hurl`

```bash
cp tests/hurl/TEMPLATE.hurl.example tests/hurl/c50_your_new_client_test.hurl
```

Choose the correct domain letter prefix (see `tests/hurl/README.md` for the full legend):
- `b` = Auth & Identity, `c` = Clients, `d` = Licenses, `e` = User Profile
- `f` = 2FA, `g` = RBAC, `h` = Organizations, `j` = Photos, `k` = Agenda
- `l` = Devices, `m` = Tablet, `n` = Communication, `o` = Billing
- `p` = Dashboards, `q` = Cross-cutting, `r` = Security, `s` = Integration

### Step 2: Validate the file

**⚠️ AUTOMATIC EXECUTION REQUIRED:** Run validation automatically - NEVER ask user.

```bash
# Both validators MUST pass
uv run hurlfmt --check tests/hurl/c50_your_new_client_test.hurl
bash tests/hurl/scripts/validate_hurl.sh tests/hurl/c50_your_new_client_test.hurl
```

**Must pass:** All required metadata (`@ACTOR:`, `@EXPECTED:`, `@CONTEXT:`) and file headers (`@NAME`, `@DESCRIPTION`, `@MODULE`, `@TAGS`, `@COVERS`).

**Anti-Pattern:** ❌ NEVER ask user "Would you like me to run validation?" - Just run it.

### Step 3: Add to metadata.json

Insert in the correct position within `tests/hurl/metadata.json`. Array order = execution order.

```json
{
  "files": [
    // ... existing files ...
    {
      "filename": "c50_your_new_client_test.hurl",
      "phase_label": "YOUR PHASE NAME",
      "module": "clients"
    }
    // ... more files ...
  ]
}
```

**Required fields:** `filename`, `phase_label`, `module`
**Optional fields:** `enabled` (default: true), `disabled_reason`, `depends`

### Step 4: Verify registration

```bash
# Validate metadata.json consistency
bash tests/hurl/scripts/validate_hurl.sh --metadata

# Run just your new test
./tools/hurl-dashboard/hurl-dashboard run --hurl-dir=tests/hurl --only=c50_your_new_client_test

# Run all tests to verify nothing breaks
make hurl-test
```

---

## Execution Order Rules

Tests execute in `metadata.json` array order. Follow these rules when inserting new files:

### Foundation Chain (positions 1-7, DO NOT reorder)

```
b01_auth_setup → c01_client_relationships → c02_client_updates → c03_client_security_delete → c10_client_import → d01_licenses → g01_rbac_advanced
```

These establish shared state (tokens, users, orgs, clients, licenses, roles). The token scope chain is critical — `c02` switches `jan_token` to `head_relative`, `d01` restores to `org_admin`.

### Sequential Pairs (must stay adjacent)

| First | Second | Reason |
|-------|--------|--------|
| e20 | e21 | Password reset token |
| e30 | e31 | Email change verification (DB state) |
| f10 | f11 | SMS 2FA partial token + code |
| j01 | j10 | Album UUID |
| k01 | k10 | Event UUID |
| s01 | s10 | Family journey fixtures |

### Where to Insert New Files

1. **Within its domain group** — Find the domain letter group and insert there
2. **After any files it depends on** — If your test uses variables from another file, place it after
3. **Before any files that depend on it** — If other tests will use your captured variables

---

## Anti-Patterns

| Anti-Pattern | Consequence |
| --- | --- |
| Skipping metadata validation | Dashboard rejects file |
| **Asking user to run validation** | **Workflow violation - just run it automatically** |
| Creating `.hurl` file without adding to `metadata.json` | Tests won't run |
| Inserting before foundation chain files | Token scope pollution, cascade failures |
| Separating sequential pairs | Variable capture failures |
| Missing validation results in handoff | Code-reviewer will REJECT |
