# Create the original.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl put initial", "description": "before", "priority": 2 }
HTTP 201
[Captures]
task_id: jsonpath "$.id"
created_at: jsonpath "$.created_at"

# PUT fully replaces every mutable field. ``description`` omitted from payload
# becomes null on the row — PUT is replace, not merge.
PUT {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "title": "hurl put replaced", "priority": 5, "status": "in_progress" }
HTTP 200
[Asserts]
jsonpath "$.id" == {{task_id}}
jsonpath "$.title" == "hurl put replaced"
jsonpath "$.description" == null
jsonpath "$.priority" == 5
jsonpath "$.status" == "in_progress"
# created_at is immutable across PUT.
jsonpath "$.created_at" == "{{created_at}}"

# Server-owned ``id`` in body → 422 read_only_field.
PUT {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "id": 9999, "title": "hurl put replaced", "priority": 5 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "read_only_field"
jsonpath "$.error.details.field" == "id"

# PUT to non-existent id → 404.
PUT {{base_url}}/v1/tasks/9999999
Content-Type: application/json
{ "title": "hurl put missing", "priority": 1 }
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
