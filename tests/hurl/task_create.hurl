# POST /v1/tasks — 201 Created, server-owned fields populated, X-Request-ID echoed.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl create A",
  "description": "first hurl-created task",
  "priority": 4
}
HTTP 201
[Captures]
task_id: jsonpath "$.id"
[Asserts]
jsonpath "$.id" isInteger
jsonpath "$.title" == "hurl create A"
jsonpath "$.description" == "first hurl-created task"
jsonpath "$.status" == "new"
jsonpath "$.priority" == 4
jsonpath "$.created_at" matches "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]+)?Z$"
header "X-Request-ID" matches "[0-9a-f-]{36}"

# Round-trip GET confirms persistence.
GET {{base_url}}/v1/tasks/{{task_id}}
HTTP 200
[Asserts]
jsonpath "$.id" == {{task_id}}
jsonpath "$.title" == "hurl create A"
