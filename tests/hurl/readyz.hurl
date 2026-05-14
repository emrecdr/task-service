# Readiness probe — succeeds only when the DB session round-trip works.
GET {{base_url}}/readyz
HTTP 200
[Asserts]
jsonpath "$.status" == "ready"
header "X-Request-ID" matches "[0-9a-f-]{36}"
