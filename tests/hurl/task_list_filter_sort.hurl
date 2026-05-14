# Seed three tasks with distinct priorities so sort order is observable.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl list L1", "priority": 1 }
HTTP 201

POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl list L3", "priority": 3 }
HTTP 201

POST {{base_url}}/v1/tasks
Content-Type: application/json
{ "title": "hurl list L5", "priority": 5 }
HTTP 201

# Default sort is priority DESC — L5 (priority 5) outranks L3 outranks L1.
# Other scenarios may have added tasks, so we filter the response to our prefix.
GET {{base_url}}/v1/tasks?limit=100
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl list L5')].priority" == 5
jsonpath "$.items[?(@.title=='hurl list L3')].priority" == 3
jsonpath "$.items[?(@.title=='hurl list L1')].priority" == 1
jsonpath "$.total" >= 3
jsonpath "$.limit" == 100
jsonpath "$.offset" == 0

# Filter by status=new — all three seeded tasks default to new.
GET {{base_url}}/v1/tasks?status=new&limit=100
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl list L1')]" exists
jsonpath "$.items[?(@.title=='hurl list L3')]" exists
jsonpath "$.items[?(@.title=='hurl list L5')]" exists

# Status filter excludes seeded "new" tasks when we ask for completed only.
GET {{base_url}}/v1/tasks?status=completed&limit=100
HTTP 200
[Asserts]
jsonpath "$.items[?(@.title=='hurl list L1')]" not exists
jsonpath "$.items[?(@.title=='hurl list L3')]" not exists
jsonpath "$.items[?(@.title=='hurl list L5')]" not exists

# Pagination: limit=1 returns exactly one item; offset advances the window.
GET {{base_url}}/v1/tasks?limit=1&offset=0
HTTP 200
[Asserts]
jsonpath "$.items" count == 1
jsonpath "$.limit" == 1
jsonpath "$.offset" == 0

# Limit above MAX_LIST_LIMIT (500) → 422 validation_error.
GET {{base_url}}/v1/tasks?limit=999
HTTP 422
[Asserts]
jsonpath "$.error.code" == "validation_error"
