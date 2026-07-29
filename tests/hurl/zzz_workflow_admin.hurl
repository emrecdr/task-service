# Workflow admin + enforcement: seeded GET → invalid PUT 422 → strand 409 →
# restrictive PUT → illegal PATCH 409 → transitions listing.
# zzz_ prefix: runs last (--jobs 1, alphabetical) because the restrictive
# definition it installs governs any tasks created after it. The compose
# container is fresh per run, so no restore step is needed.

# 1. The seeded definition is active: version 1, three states.
GET {{base_url}}/v1/workflow
HTTP 200
[Asserts]
jsonpath "$.version" == 1
jsonpath "$.definition.states" count == 3
jsonpath "$.definition.transitions" count == 6

# 2. Invalid definition: every problem reported at once, nothing stored.
PUT {{base_url}}/v1/workflow
Content-Type: application/json
{
  "states": ["a", "a"],
  "transitions": [{ "name": "", "from": "a", "to": "ghost" }]
}
HTTP 422
[Asserts]
jsonpath "$.error.code" == "invalid_workflow_definition"
jsonpath "$.error.details.errors" count == 3
jsonpath "$.error.request_id" matches "[0-9a-f-]{36}"

# 3. A task occupying "new" blocks any definition that drops the state.
POST {{base_url}}/v1/tasks
Content-Type: application/json
{
  "title": "hurl workflow strand guard",
  "priority": 2
}
HTTP 201
[Captures]
strand_task_id: jsonpath "$.id"

PUT {{base_url}}/v1/workflow
Content-Type: application/json
{
  "states": [{ "name": "open", "initial": true }, "closed"],
  "transitions": [{ "name": "Close", "from": "open", "to": "closed" }]
}
HTTP 409
[Asserts]
jsonpath "$.error.code" == "workflow_states_in_use"
# Earlier scenarios in the sequential run also left tasks in "new" — the
# exact count is theirs to change; the guard only owes an occupied-state entry.
jsonpath "$.error.details.states.new" >= 1

# 4. A restrictive definition that keeps the three states installs fine.
PUT {{base_url}}/v1/workflow
Content-Type: application/json
{
  "states": [
    { "name": "new", "initial": true },
    "in_progress",
    { "name": "completed", "completes": true }
  ],
  "transitions": [
    { "name": "Start work", "from": "new", "to": "in_progress", "color": "#1f6feb" },
    { "name": "Finish", "from": "in_progress", "to": "completed" }
  ]
}
HTTP 200
[Asserts]
jsonpath "$.version" == 2

# 5. The workflow now governs task writes: new → completed is illegal.
PATCH {{base_url}}/v1/tasks/{{strand_task_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 409
[Asserts]
jsonpath "$.error.code" == "invalid_transition"
jsonpath "$.error.details.from" == "new"
jsonpath "$.error.details.to" == "completed"
jsonpath "$.error.details.allowed" count == 1
jsonpath "$.error.details.allowed[0]" == "in_progress"

# 6. Transitions listing: the UI-button view, meta passed through.
GET {{base_url}}/v1/tasks/{{strand_task_id}}/transitions
HTTP 200
[Asserts]
jsonpath "$.task_id" == {{strand_task_id}}
jsonpath "$.status" == "new"
jsonpath "$.transitions" count == 1
jsonpath "$.transitions[0].name" == "Start work"
jsonpath "$.transitions[0].to" == "in_progress"
jsonpath "$.transitions[0].meta.color" == "#1f6feb"

# 7. The legal path still works end to end under the restrictive definition.
PATCH {{base_url}}/v1/tasks/{{strand_task_id}}
Content-Type: application/json
{ "status": "in_progress" }
HTTP 200

PATCH {{base_url}}/v1/tasks/{{strand_task_id}}
Content-Type: application/json
{ "status": "completed" }
HTTP 200
[Asserts]
jsonpath "$.status" == "completed"
