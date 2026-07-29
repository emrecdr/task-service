from typing import Any

from app.core.errors import ErrorCode
from app.services.workflows.infrastructure.seed import default_workflow
from app.services.workflows.serialization import workflow_to_document
from httpx import AsyncClient

from tests.conftest import CreateTask, assert_error


def _definition_with_review() -> dict[str, Any]:
    """The seeded three states plus a reachable ``review`` column."""
    document = workflow_to_document(default_workflow())
    document["states"].append("review")
    document["transitions"].append({"name": "Request review", "from": "in_progress", "to": "review"})
    document["transitions"].append({"name": "Approve", "from": "review", "to": "completed"})
    return document


async def test_get_returns_seeded_definition(client: AsyncClient) -> None:
    r = await client.get("/v1/workflow")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["created_at"].endswith("Z")
    assert body["definition"] == workflow_to_document(default_workflow())


async def test_put_stores_new_version_and_get_reflects_it(client: AsyncClient) -> None:
    document = _definition_with_review()

    r = await client.put("/v1/workflow", json=document)

    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    fetched = await client.get("/v1/workflow")
    assert fetched.json()["version"] == 2
    assert "review" in {s if isinstance(s, str) else s["name"] for s in fetched.json()["definition"]["states"]}


async def test_put_invalid_definition_collects_all_errors(client: AsyncClient) -> None:
    document = {"states": ["a", "a"], "transitions": [{"name": "", "from": "a", "to": "ghost"}]}

    r = await client.put("/v1/workflow", json=document)

    err = assert_error(r, 422, ErrorCode.INVALID_WORKFLOW_DEFINITION)
    assert len(err["details"]["errors"]) == 3


async def test_put_rejects_server_owned_version_key(client: AsyncClient) -> None:
    document = workflow_to_document(default_workflow()) | {"version": 99}

    r = await client.put("/v1/workflow", json=document)

    err = assert_error(r, 422, ErrorCode.INVALID_WORKFLOW_DEFINITION)
    assert any("unknown top-level key: 'version'" in e for e in err["details"]["errors"])


async def test_put_stranding_occupied_state_returns_409(client: AsyncClient, create_task: CreateTask) -> None:
    await create_task("occupies new")
    document = {
        "states": [{"name": "open", "initial": True}, "closed"],
        "transitions": [{"name": "Close", "from": "open", "to": "closed"}],
    }

    r = await client.put("/v1/workflow", json=document)

    err = assert_error(r, 409, ErrorCode.WORKFLOW_STATES_IN_USE)
    assert err["details"] == {"states": {"new": 1}}
    # The active definition must be unchanged.
    assert (await client.get("/v1/workflow")).json()["version"] == 1


async def test_put_non_object_body_returns_validation_error(client: AsyncClient) -> None:
    r = await client.put("/v1/workflow", json=["not", "an", "object"])

    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_put_twice_appends_versions(client: AsyncClient) -> None:
    document = _definition_with_review()

    first = await client.put("/v1/workflow", json=document)
    second = await client.put("/v1/workflow", json=document)

    assert first.json()["version"] == 2
    assert second.json()["version"] == 3
    assert (await client.get("/v1/workflow")).json()["version"] == 3
