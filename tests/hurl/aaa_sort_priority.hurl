# Sort-by-priority E2E coverage.
#
# Runs FIRST in the suite (``aaa_`` prefix) so the in-memory SQLite is empty
# and ``items[N]`` absolute-index assertions are deterministic. Other files
# share the DB and use JSONPath title-prefix filters instead.

# Seed three priorities in non-monotonic order so creation-order ≠ priority-order.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl sort P3", "priority": 3 }
HTTP 201
[Captures]
p3_id: jsonpath "$.id"

POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl sort P1", "priority": 1 }
HTTP 201
[Captures]
p1_id: jsonpath "$.id"

POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl sort P5", "priority": 5 }
HTTP 201
[Captures]
p5_id: jsonpath "$.id"

# Default sort — priority DESC per FRD §3.1.
GET {{base_url}}/v1/tasks
HTTP 200
[Asserts]
jsonpath "$.total" == 3
jsonpath "$.items" count == 3
jsonpath "$.items[0].title" == "hurl sort P5"
jsonpath "$.items[0].priority" == 5
jsonpath "$.items[1].title" == "hurl sort P3"
jsonpath "$.items[1].priority" == 3
jsonpath "$.items[2].title" == "hurl sort P1"
jsonpath "$.items[2].priority" == 1

# Explicit DESC — must match the default.
GET {{base_url}}/v1/tasks?order_by=priority&order_dir=desc
HTTP 200
[Asserts]
jsonpath "$.items[0].priority" == 5
jsonpath "$.items[1].priority" == 3
jsonpath "$.items[2].priority" == 1

# Reverse direction must invert the listing exactly.
GET {{base_url}}/v1/tasks?order_by=priority&order_dir=asc
HTTP 200
[Asserts]
jsonpath "$.items[0].priority" == 1
jsonpath "$.items[1].priority" == 3
jsonpath "$.items[2].priority" == 5

# Tie-break: repository uses ``created_at ASC`` so older P3 precedes newer P3-late.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl sort P3-late", "priority": 3 }
HTTP 201
[Captures]
p3late_id: jsonpath "$.id"

GET {{base_url}}/v1/tasks?order_by=priority&order_dir=desc
HTTP 200
[Asserts]
jsonpath "$.total" == 4
jsonpath "$.items[0].title" == "hurl sort P5"
jsonpath "$.items[1].title" == "hurl sort P3"
jsonpath "$.items[2].title" == "hurl sort P3-late"
jsonpath "$.items[3].title" == "hurl sort P1"

# Unknown ``order_by`` value → 422.
GET {{base_url}}/v1/tasks?order_by=created_at
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Unknown ``order_dir`` value → 422.
GET {{base_url}}/v1/tasks?order_dir=sideways
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Cleanup — restore the empty-DB invariant for downstream files.
DELETE {{base_url}}/v1/tasks/{{p1_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{p3_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{p3late_id}}
HTTP 204

DELETE {{base_url}}/v1/tasks/{{p5_id}}
HTTP 204
