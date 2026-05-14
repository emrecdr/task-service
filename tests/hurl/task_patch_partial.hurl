# Create the original.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl patch original", "description": "untouched", "priority": 3 }
HTTP 201
[Captures]
task_id: jsonpath "$.id"

# PATCH a single field — all other fields remain.
PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "priority": 5 }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task_id}}
jsonpath "$.title" == "hurl patch original"
jsonpath "$.description" == "untouched"
jsonpath "$.priority" == 5
jsonpath "$.status" == "new"

# PATCH with empty body → 422 empty_update.
PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{}
HTTP 422
[Asserts]
jsonpath "$.error.code" == "empty_update"

# PATCH with server-owned ``created_at`` → 422 read_only_field.
PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "created_at": "2020-01-01T00:00:00Z" }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "read_only_field"
jsonpath "$.error.details.field" == "created_at"

# PATCH to non-existent id → 404.
PATCH {{base_url}}/v1/tasks/9999999
Content-Type: application/json
{ "priority": 1 }
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
