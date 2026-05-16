# Empty title → 422 validation_error.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "", "priority": 3 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"
jsonpath "$.error.request_id" matches "[0-9a-f-]{36}"

# Whitespace-only title → 422 validation_error.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "   ", "priority": 3 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Priority above max (5) → 422.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl validation P-high", "priority": 6 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Priority below min (1) → 422.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl validation P-low", "priority": 0 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Unknown status value → 422.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl validation status", "priority": 3, "status": "shipped" }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"

# Client supplies server-owned id → 422 read_only_field (extra="forbid").
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "id": 12345, "title": "hurl validation id", "priority": 3 }
HTTP 422
[Asserts]
jsonpath "$.error.code" == "read_only_field"
jsonpath "$.error.details.field" == "id"
