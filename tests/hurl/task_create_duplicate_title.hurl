# First create succeeds.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl duplicate B", "priority": 3 }
HTTP 201
[Asserts]
jsonpath "$.title" == "hurl duplicate B"

# Same title — exact match — must 409 with duplicate_task envelope.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl duplicate B", "priority": 2 }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"
jsonpath "$.error.message" exists
jsonpath "$.error.details.title" == "hurl duplicate B"
jsonpath "$.error.request_id" matches "[0-9a-f-]{36}"

# Title differing only in case/whitespace — same title_key, also 409.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "  Hurl DUPLICATE b  ", "priority": 2 }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "duplicate_task"
