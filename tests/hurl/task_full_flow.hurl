# Full-flow scenario across the 5 mutating endpoints + filtered list:
#   1)  create 4 tasks (status=new)
#   2)  list all — assert the 4 are present
#   3)  PATCH task #1 (priority + description) — assert the field changed
#   4)  GET task #1 by id — re-assert the new field values
#   5)  DELETE task #3 — assert 204 + a follow-up GET 404
#   6)  list again — assert #1, #2, #4 present; #3 gone
#   7)  PATCH task #2 status: new → in_progress
#   8)  list filtered by status=in_progress — ONLY #2 (#4 is still "new")
#   9)  PATCH task #2 status: in_progress → completed
#  10)  list filtered by status=completed — ONLY #2
#  11)  multi-value status filter (?status=new&status=completed) →
#       #1 + #2 + #4 (delta is still "new")
#  12)  PUT task #4 — full replace (the only verb the rest of the flow
#       doesn't exercise) — sets status=in_progress
#  13)  GET task #4 — verify the full replace took effect
#  14)  list filtered by status=in_progress — ONLY #4 (after PUT)
#  15)  conflict-on-update on #1 → 409 duplicate_task
#  16)  empty PATCH on #1 → 422 empty_update
#  17)  PATCH with server-owned id on #1 → 422 read_only_field
#  18)  operations on the already-deleted #3 → 404 envelope
#  19)  cleanup: DELETE #1, #2, #4
#
# Title prefix ``hurl flow`` keeps this scenario isolated from the other
# Hurl files under ``--jobs 1`` against the shared in-memory SQLite.

# ───────────────────────────────────────────────────────────────────────────
# 1) Create four tasks with priorities 1/2/3/4, capture each id.
# ───────────────────────────────────────────────────────────────────────────
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow alpha",
  "priority": 1
}
HTTP 201
[Captures]
task1_id: jsonpath "$.id"
[Asserts]
jsonpath "$.status" == "new"

POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow beta",
  "priority": 2
}
HTTP 201
[Captures]
task2_id: jsonpath "$.id"
[Asserts]
jsonpath "$.status" == "new"

POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow gamma",
  "priority": 3
}
HTTP 201
[Captures]
task3_id: jsonpath "$.id"
[Asserts]
jsonpath "$.status" == "new"

POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow delta",
  "priority": 4
}
HTTP 201
[Captures]
task4_id: jsonpath "$.id"
[Asserts]
jsonpath "$.status" == "new"

# ───────────────────────────────────────────────────────────────────────────
# 1b) Duplicate-title rejection on CREATE — re-creating task #1 with a
#     casing/whitespace variant must be rejected with 409 duplicate_task. The
#     uniqueness key is ``title_key = title.strip().casefold()`` (see CLAUDE.md
#     "Key conventions"), so ``"hurl flow ALPHA "`` collides with the
#     already-stored ``"hurl flow alpha"``.
# ───────────────────────────────────────────────────────────────────────────
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow ALPHA ",
  "priority": 1
}
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"

# ───────────────────────────────────────────────────────────────────────────
# 1c) Duplicate-title rejection on RENAME — the same uniqueness rule applies
#     to PATCH/PUT, not just create. Attempting to rename delta into a
#     casing/whitespace variant of alpha's title must also 409. A follow-up
#     GET on delta confirms its title and priority were not partially mutated
#     by the rejected request (transactional integrity).
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task4_id}}
Content-Type: application/json
{ "title": " hurl flow ALPHA " }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"

GET {{base_url}}/v1/tasks/{{task4_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task4_id}}
jsonpath "$.title" == "hurl flow delta"
jsonpath "$.priority" == 4
jsonpath "$.status" == "new"

# ───────────────────────────────────────────────────────────────────────────
# 2) List all — all four flow tasks must be present (the 409s above must not
#     have created a 5th row or mutated delta).
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists

# ───────────────────────────────────────────────────────────────────────────
# 3) PATCH task #1 — change priority and add a description.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{
  "priority": 5,
  "description": "updated via full-flow scenario"
}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task1_id}}
jsonpath "$.title" == "hurl flow alpha"
jsonpath "$.priority" == 5
jsonpath "$.description" == "updated via full-flow scenario"
jsonpath "$.status" == "new"

# ───────────────────────────────────────────────────────────────────────────
# 4) GET task #1 by id — the patched fields must round-trip.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks/{{task1_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task1_id}}
jsonpath "$.priority" == 5
jsonpath "$.description" == "updated via full-flow scenario"
jsonpath "$.status" == "new"

# ───────────────────────────────────────────────────────────────────────────
# 5) DELETE task #3 — 204 + the resource must be gone on follow-up GET.
# ───────────────────────────────────────────────────────────────────────────
DELETE {{base_url}}/v1/tasks/{{task3_id}}
HTTP 204

GET {{base_url}}/v1/tasks/{{task3_id}}
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"

# ───────────────────────────────────────────────────────────────────────────
# 6) List again — task #1, #2, #4 still present; #3 has vanished.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# ───────────────────────────────────────────────────────────────────────────
# 7) PATCH task #2 status: new → in_progress.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task2_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task2_id}}
jsonpath "$.status" == "in_progress"

# ───────────────────────────────────────────────────────────────────────────
# 8) List filtered by status=in_progress — ONLY task #2.
#    Task #1 (new), task #3 (deleted), task #4 (new) → must NOT appear.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?status=in_progress&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" not exists

# ───────────────────────────────────────────────────────────────────────────
# 9) Promote task #2 further: in_progress → completed.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task2_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task2_id}}
jsonpath "$.status" == "completed"

# ───────────────────────────────────────────────────────────────────────────
# 10) Filter by status=completed — task #2 is the only flow task with that
#     status; alpha (new), gamma (deleted), delta (new) must not appear.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?status=completed&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" not exists

# ───────────────────────────────────────────────────────────────────────────
# 11) Multi-value status filter — the ``status`` query param accepts
#     repeated values (FastAPI maps ``list[Status]`` to ``?status=A&status=B``).
#     Asking for both "new" and "completed" must return alpha + beta + delta.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?status=new&status=completed&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# ───────────────────────────────────────────────────────────────────────────
# 12) PUT task #4 — full replace. PUT requires every non-server-owned field
#     in the body (TaskCreate shape), and overwrites all of them at once.
#     Title stays the same so this isn't a duplicate; everything else changes.
# ───────────────────────────────────────────────────────────────────────────
PUT {{base_url}}/v1/tasks/{{task4_id}}
Content-Type: application/json
{
  "title": "hurl flow delta",
  "priority": 5,
  "description": "fully replaced via PUT",
  "status": "in_progress"
}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task4_id}}
jsonpath "$.title" == "hurl flow delta"
jsonpath "$.priority" == 5
jsonpath "$.description" == "fully replaced via PUT"
jsonpath "$.status" == "in_progress"

# ───────────────────────────────────────────────────────────────────────────
# 13) GET task #4 — verify the full replace persisted exactly.
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks/{{task4_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task4_id}}
jsonpath "$.title" == "hurl flow delta"
jsonpath "$.priority" == 5
jsonpath "$.description" == "fully replaced via PUT"
jsonpath "$.status" == "in_progress"

# ───────────────────────────────────────────────────────────────────────────
# 14) List filtered by status=in_progress — after the PUT, delta is the
#     only flow task in this state (beta moved on to "completed" at step 9).
# ───────────────────────────────────────────────────────────────────────────
GET {{base_url}}/v1/tasks?status=in_progress&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# ───────────────────────────────────────────────────────────────────────────
# 15) Conflict-on-update: PATCH alpha's title to beta's title.
#     Duplicate detection runs through ``title_key`` (casefolded), not the
#     raw title, so the casing variant still collides → 409 duplicate_task.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{ "title": "HURL FLOW BETA" }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"

# ───────────────────────────────────────────────────────────────────────────
# 16) Empty PATCH body → 422 empty_update envelope.
#     Runtime defense even though OpenAPI also documents ``minProperties: 1``.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{}
HTTP 422
[Asserts]
jsonpath "$.error.code" == "empty_update"

# ───────────────────────────────────────────────────────────────────────────
# 17) PATCH with a server-owned field → 422 read_only_field envelope.
# ───────────────────────────────────────────────────────────────────────────
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{ "id": 999 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "read_only_field"
jsonpath "$.error.details.field" == "id"

# ───────────────────────────────────────────────────────────────────────────
# 18) Operations on the already-deleted task #3 must all 404 cleanly.
#     DELETE on a missing resource is NOT idempotent in this contract — it
#     returns 404 with the canonical envelope (FRD §3.1).
# ───────────────────────────────────────────────────────────────────────────
DELETE {{base_url}}/v1/tasks/{{task3_id}}
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"

PATCH {{base_url}}/v1/tasks/{{task3_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"

# ───────────────────────────────────────────────────────────────────────────
# 19) Final cleanup — remove alpha, beta, and delta so the shared in-memory
#     DB has no flow residue. (Other Hurl files filter by their own title
#     prefixes, so this is hygiene rather than correctness.)
# ───────────────────────────────────────────────────────────────────────────
DELETE {{base_url}}/v1/tasks/{{task1_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{task2_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{task4_id}}
HTTP 204
