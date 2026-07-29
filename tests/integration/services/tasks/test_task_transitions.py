from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import CreateTask, assert_error


async def test_transitions_lists_legal_moves_for_seeded_workflow(client: AsyncClient, create_task: CreateTask) -> None:
    task_id = await create_task("x")

    r = await client.get(f"/v1/tasks/{task_id}/transitions")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task_id"] == task_id
    assert body["status"] == "new"
    # Seed: from "new" both other states are reachable.
    assert {(t["name"], t["to"]) for t in body["transitions"]} == {
        ("Start work", "in_progress"),
        ("Complete", "completed"),
    }


async def test_transitions_passes_definition_meta_through(client: AsyncClient, create_task: CreateTask) -> None:
    document = {
        "states": [{"name": "new", "initial": True}, "in_progress", {"name": "completed", "completes": True}],
        "transitions": [
            {"name": "Start work", "from": "new", "to": "in_progress", "color": "#1f6feb"},
            {"name": "Finish", "from": "in_progress", "to": "completed"},
            {"name": "Send back", "from": "in_progress", "to": "new"},
        ],
    }
    put = await client.put("/v1/workflow", json=document)
    assert put.status_code == 200, put.text
    task_id = await create_task("x")

    r = await client.get(f"/v1/tasks/{task_id}/transitions")

    assert r.status_code == 200, r.text
    (transition,) = r.json()["transitions"]
    assert transition == {"name": "Start work", "to": "in_progress", "meta": {"color": "#1f6feb"}}


async def test_transitions_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.get("/v1/tasks/99999/transitions")
    assert_error(r, 404, ErrorCode.TASK_NOT_FOUND)
