# Full-flow scenario across all 5 mutating endpoints + filtered list.
# Title prefix ``hurl flow`` keeps this isolated from other Hurl files
# under ``--jobs 1`` against the shared in-memory SQLite.

# 1) Create four tasks with priorities 1/2/3/4, capture each id.
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

# 1b) Duplicate-title rejection on CREATE — casing/whitespace variants collide on ``title_key``.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl flow ALPHA ",
  "priority": 1
}
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"

# 1c) Duplicate-title rejection on PATCH rename; follow-up GET confirms delta was not mutated.
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

# 2) List all — the 409s above must not have created a 5th row or mutated delta.
GET {{base_url}}/v1/tasks?limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists

# 3) PATCH task #1 — change priority and add a description.
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

# 4) GET task #1 — patched fields must round-trip.
GET {{base_url}}/v1/tasks/{{task1_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task1_id}}
jsonpath "$.priority" == 5
jsonpath "$.description" == "updated via full-flow scenario"
jsonpath "$.status" == "new"

# 5) DELETE task #3 — 204 + follow-up GET 404.
DELETE {{base_url}}/v1/tasks/{{task3_id}}
HTTP 204

GET {{base_url}}/v1/tasks/{{task3_id}}
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"

# 6) List again — #1, #2, #4 present; #3 gone.
GET {{base_url}}/v1/tasks?limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# 7) PATCH task #2 status: new → in_progress.
PATCH {{base_url}}/v1/tasks/{{task2_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task2_id}}
jsonpath "$.status" == "in_progress"

# 8) Filter status=in_progress — ONLY task #2.
GET {{base_url}}/v1/tasks?status=in_progress&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" not exists

# 9) Promote task #2: in_progress → completed.
PATCH {{base_url}}/v1/tasks/{{task2_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task2_id}}
jsonpath "$.status" == "completed"

# 10) Filter status=completed — ONLY task #2.
GET {{base_url}}/v1/tasks?status=completed&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" not exists

# 11) Multi-value status filter — ``?status=new&status=completed`` → alpha + beta + delta.
GET {{base_url}}/v1/tasks?status=new&status=completed&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow alpha')]" exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" exists
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# 12) PUT task #4 — full replace; title unchanged so no collision.
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

# 13) GET task #4 — replace persisted exactly.
GET {{base_url}}/v1/tasks/{{task4_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task4_id}}
jsonpath "$.title" == "hurl flow delta"
jsonpath "$.priority" == 5
jsonpath "$.description" == "fully replaced via PUT"
jsonpath "$.status" == "in_progress"

# 14) Filter status=in_progress — delta is the only flow task in this state.
GET {{base_url}}/v1/tasks?status=in_progress&limit=500
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl flow delta')]" exists
jsonpath "$.items[?(@.title=='hurl flow alpha')]" not exists
jsonpath "$.items[?(@.title=='hurl flow beta')]" not exists
jsonpath "$.items[?(@.title=='hurl flow gamma')]" not exists

# 15) Conflict on rename — casing variant still collides via ``title_key``.
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{ "title": "HURL FLOW BETA" }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"

# 16) Empty PATCH body → 422 empty_update.
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{}
HTTP 422
[Asserts]
jsonpath "$.error.code" == "empty_update"

# 17) PATCH with server-owned field → 422 read_only_field.
PATCH {{base_url}}/v1/tasks/{{task1_id}}
Content-Type: application/json
{ "id": 999 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "read_only_field"
jsonpath "$.error.details.field" == "id"

# 18) Operations on the already-deleted task #3 all 404 (DELETE is not idempotent here).
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

# 19) Cleanup — remove alpha, beta, delta.
DELETE {{base_url}}/v1/tasks/{{task1_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{task2_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{task4_id}}
HTTP 204
