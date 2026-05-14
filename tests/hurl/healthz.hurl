# Liveness probe — must answer 200 with a stable body shape; no DB I/O.
GET {{base_url}}/healthz
HTTP 200
[Asserts]
jsonpath "$.status" == "ok"
header "X-Request-ID" matches "[0-9a-f-]{36}"
