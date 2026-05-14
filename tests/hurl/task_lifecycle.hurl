# Full lifecycle: create → in_progress → completed → delete → 404.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl lifecycle",
  "priority": 4
}
HTTP 201
[Captures]
task_id: jsonpath "$.id"
[Asserts]
jsonpath "$.title" == "hurl lifecycle"
jsonpath "$.status" == "new"
header "X-Request-ID" matches "[0-9a-f-]{36}"

PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 200
[Asserts]
jsonpath "$.status" == "in_progress"

PATCH {{base_url}}/v1/tasks/{{task_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 200
[Asserts]
jsonpath "$.status" == "completed"

DELETE {{base_url}}/v1/tasks/{{task_id}}
HTTP 204

GET {{base_url}}/v1/tasks/{{task_id}}
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
