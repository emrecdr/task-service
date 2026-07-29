"""End-to-end enforcement: a restrictive definition installed over HTTP governs task writes."""

from typing import Any

from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import CreateTask, assert_error

# Single entry, one forward path; completed is terminal and completing.
_STRICT: dict[str, Any] = {
    "states": [{"name": "new", "initial": True}, "in_progress", {"name": "completed", "completes": True}],
    "transitions": [
        {"name": "Start work", "from": "new", "to": "in_progress"},
        {"name": "Finish", "from": "in_progress", "to": "completed"},
    ],
}


async def _install_strict(client: AsyncClient) -> None:
    r = await client.put("/v1/workflow", json=_STRICT)
    assert r.status_code == 200, r.text


async def test_create_defaults_to_workflow_default_entry(client: AsyncClient) -> None:
    await _install_strict(client)

    r = await client.post("/v1/tasks", json={"title": "x", "priority": 3})

    assert r.status_code == 201, r.text
    assert r.json()["status"] == "new"


async def test_create_into_non_entry_state_returns_409(client: AsyncClient) -> None:
    await _install_strict(client)

    r = await client.post("/v1/tasks", json={"title": "x", "priority": 3, "status": "completed"})

    err = assert_error(r, 409, ErrorCode.INVALID_TRANSITION)
    assert err["details"] == {"from": None, "to": "completed", "allowed": ["new"]}


async def test_create_with_unknown_state_returns_422(client: AsyncClient) -> None:
    await _install_strict(client)

    r = await client.post("/v1/tasks", json={"title": "x", "priority": 3, "status": "ghost"})

    err = assert_error(r, 422, ErrorCode.VALIDATION_ERROR)
    assert err["details"] == {
        "field": "status",
        "value": "ghost",
        "known_states": ["new", "in_progress", "completed"],
    }


async def test_create_explicit_null_status_still_returns_422(client: AsyncClient) -> None:
    r = await client.post("/v1/tasks", json={"title": "x", "priority": 3, "status": None})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_patch_illegal_move_returns_409_with_allowed_list(client: AsyncClient, create_task: CreateTask) -> None:
    await _install_strict(client)
    task_id = await create_task("x")

    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "completed"})

    err = assert_error(r, 409, ErrorCode.INVALID_TRANSITION)
    assert err["details"] == {"from": "new", "to": "completed", "allowed": ["in_progress"]}
    # The rejected move must not mutate the row.
    assert (await client.get(f"/v1/tasks/{task_id}")).json()["status"] == "new"


async def test_patch_legal_path_reaches_completed(client: AsyncClient, create_task: CreateTask) -> None:
    await _install_strict(client)
    task_id = await create_task("x")

    assert (await client.patch(f"/v1/tasks/{task_id}", json={"status": "in_progress"})).status_code == 200
    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "completed"})

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"


async def test_put_omitting_status_on_mid_flow_task_returns_409(client: AsyncClient, create_task: CreateTask) -> None:
    """PUT resolves omitted status to default_entry; under a restrictive
    definition that back-move is a loud 409, never a silent reset."""
    await _install_strict(client)
    task_id = await create_task("x")
    await client.patch(f"/v1/tasks/{task_id}", json={"status": "in_progress"})

    r = await client.put(f"/v1/tasks/{task_id}", json={"title": "x", "priority": 3})

    err = assert_error(r, 409, ErrorCode.INVALID_TRANSITION)
    assert err["details"]["from"] == "in_progress"
    assert err["details"]["to"] == "new"


async def test_seeded_default_preserves_any_to_any_behavior(client: AsyncClient, create_task: CreateTask) -> None:
    """Without a custom definition the Phase-1 contract holds: any → any."""
    task_id = await create_task("x")

    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "completed"})
    assert r.status_code == 200, r.text
    r = await client.patch(f"/v1/tasks/{task_id}", json={"status": "new"})
    assert r.status_code == 200, r.text
