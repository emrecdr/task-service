"""Workflow role-guards and WIP-limits enforced end-to-end over HTTP.

Role-guards read the actor's roles from the provisional ``X-Roles`` header; WIP-limits read
occupancy from the DB. Both are declared as ``meta`` on the active workflow definition.
"""

from typing import Any

from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import CreateTask, InstallWorkflow, assert_error

_ROLE_GUARDED: dict[str, Any] = {
    "states": [{"name": "new", "initial": True}, {"name": "done", "completes": True}],
    "transitions": [{"name": "Approve", "from": "new", "to": "done", "roles": ["manager"]}],
}

_WIP_LIMITED: dict[str, Any] = {
    "states": [{"name": "new", "initial": True}, {"name": "active", "wip_limit": 1}],
    "transitions": [{"name": "Activate", "from": "new", "to": "active"}],
}

# The capped state is also an entry state, so a *create* can hit the limit — that branch runs
# through ``resolve_entry``, not ``check_move``.
_WIP_LIMITED_ENTRY: dict[str, Any] = {
    "states": [{"name": "new", "initial": True}, {"name": "active", "initial": True, "wip_limit": 1}],
    "transitions": [{"name": "Activate", "from": "new", "to": "active"}],
}


class TestRoleGuards:
    async def test_guarded_move_without_the_role_is_403(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_ROLE_GUARDED)
        task_id = await create_task("t")
        resp = await client.patch(f"/v1/tasks/{task_id}", json={"status": "done"})  # no X-Roles
        err = assert_error(resp, 403, ErrorCode.TRANSITION_FORBIDDEN)
        assert err["details"]["required_roles"] == ["manager"]

    async def test_guarded_move_with_the_role_succeeds(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_ROLE_GUARDED)
        task_id = await create_task("t")
        resp = await client.patch(f"/v1/tasks/{task_id}", json={"status": "done"}, headers={"X-Roles": "manager"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "done"

    async def test_roles_header_is_comma_separated(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_ROLE_GUARDED)
        task_id = await create_task("t")
        resp = await client.patch(f"/v1/tasks/{task_id}", json={"status": "done"}, headers={"X-Roles": "dev, manager"})
        assert resp.status_code == 200, resp.text

    async def test_guarded_put_without_the_role_is_403(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        # PUT wires its own ``ActorRolesDep``; a guard reaching only PATCH would leave the
        # full-replace route unauthorized.
        await install_workflow(_ROLE_GUARDED)
        task_id = await create_task("t")
        body = {"title": "t", "description": None, "status": "done", "priority": 1}
        resp = await client.put(f"/v1/tasks/{task_id}", json=body)  # no X-Roles
        err = assert_error(resp, 403, ErrorCode.TRANSITION_FORBIDDEN)
        assert err["details"]["required_roles"] == ["manager"]

    async def test_guarded_put_with_the_role_succeeds(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_ROLE_GUARDED)
        task_id = await create_task("t")
        body = {"title": "t", "description": None, "status": "done", "priority": 1}
        resp = await client.put(f"/v1/tasks/{task_id}", json=body, headers={"X-Roles": "manager"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "done"


class TestWipLimits:
    async def test_move_into_a_full_state_is_409(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_WIP_LIMITED)
        first = await create_task("a")
        second = await create_task("b")
        ok = await client.patch(f"/v1/tasks/{first}", json={"status": "active"})
        assert ok.status_code == 200, ok.text  # fills "active" (limit 1)
        full = await client.patch(f"/v1/tasks/{second}", json={"status": "active"})
        err = assert_error(full, 409, ErrorCode.WIP_LIMIT_EXCEEDED)
        assert err["details"] == {"state": "active", "limit": 1, "current": 1}

    async def test_move_below_the_limit_succeeds(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_WIP_LIMITED)
        task_id = await create_task("a")
        ok = await client.patch(f"/v1/tasks/{task_id}", json={"status": "active"})
        assert ok.status_code == 200, ok.text

    async def test_create_into_a_full_entry_state_is_409(
        self, client: AsyncClient, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_WIP_LIMITED_ENTRY)
        first = await client.post("/v1/tasks", json={"title": "a", "status": "active", "priority": 1})
        assert first.status_code == 201, first.text  # fills "active" (limit 1)
        full = await client.post("/v1/tasks", json={"title": "b", "status": "active", "priority": 1})
        err = assert_error(full, 409, ErrorCode.WIP_LIMIT_EXCEEDED)
        assert err["details"] == {"state": "active", "limit": 1, "current": 1}

    async def test_put_into_a_full_state_is_409(
        self, client: AsyncClient, create_task: CreateTask, install_workflow: InstallWorkflow
    ) -> None:
        await install_workflow(_WIP_LIMITED)
        first = await create_task("a")
        second = await create_task("b")
        ok = await client.patch(f"/v1/tasks/{first}", json={"status": "active"})
        assert ok.status_code == 200, ok.text  # fills "active" (limit 1)
        body = {"title": "b", "description": None, "status": "active", "priority": 1}
        full = await client.put(f"/v1/tasks/{second}", json=body)
        assert_error(full, 409, ErrorCode.WIP_LIMIT_EXCEEDED)


class TestGuardMetaValidation:
    async def test_put_workflow_rejects_a_negative_wip_limit(self, client: AsyncClient) -> None:
        document = {
            "states": [{"name": "new", "initial": True}, {"name": "active", "wip_limit": -1}],
            "transitions": [{"name": "Go", "from": "new", "to": "active"}],
        }
        resp = await client.put("/v1/workflow", json=document)
        assert_error(resp, 422, ErrorCode.INVALID_WORKFLOW_DEFINITION)

    async def test_put_workflow_rejects_non_string_roles(self, client: AsyncClient) -> None:
        document = {
            "states": ["new", "done"],
            "transitions": [{"name": "Go", "from": "new", "to": "done", "roles": [1, 2]}],
        }
        resp = await client.put("/v1/workflow", json=document)
        assert_error(resp, 422, ErrorCode.INVALID_WORKFLOW_DEFINITION)
