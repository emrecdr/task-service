# Inbound X-Request-ID is echoed verbatim.
GET {{base_url}}/healthz
X-Request-ID: 11111111-2222-3333-4444-555555555555
HTTP 200
[Asserts]
header "X-Request-ID" == "11111111-2222-3333-4444-555555555555"

# Absent X-Request-ID — server generates a UUIDv4 and echoes it.
GET {{base_url}}/healthz
HTTP 200
[Asserts]
header "X-Request-ID" matches "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
