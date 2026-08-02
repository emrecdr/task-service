# Missing id on every verb that targets a single resource → 404 + task_not_found envelope.
GET {{base_url}}/v1/tasks/00000000-0000-0000-0000-000000000000
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
jsonpath "$.error.details.id" == "00000000-0000-0000-0000-000000000000"
jsonpath "$.error.request_id" matches "[0-9a-f-]{36}"

DELETE {{base_url}}/v1/tasks/00000000-0000-0000-0000-000000000000
HTTP 404
[Asserts]
jsonpath "$.error.code" == "task_not_found"
jsonpath "$.error.details.id" == "00000000-0000-0000-0000-000000000000"
