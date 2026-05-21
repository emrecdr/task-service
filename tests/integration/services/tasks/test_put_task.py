from app.core.errors import ErrorCode
from httpx import AsyncClient

from tests.conftest import CreateTask, assert_error


async def test_put_full_replace_returns_200(client: AsyncClient, create_task: CreateTask) -> None:
    task_id = await create_task("original")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"title": "replaced", "description": "d", "status": "in_progress", "priority": 5},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == task_id
    assert body["title"] == "replaced"
    assert body["description"] == "d"
    assert body["status"] == "in_progress"
    assert body["priority"] == 5


async def test_put_unknown_id_returns_404(client: AsyncClient) -> None:
    r = await client.put(
        "/v1/tasks/99999",
        json={"title": "x", "priority": 1},
    )
    assert_error(r, 404, ErrorCode.TASK_NOT_FOUND, details={"id": 99999})


async def test_put_self_title_case_variant_succeeds(client: AsyncClient, create_task: CreateTask) -> None:
    """Replacing a row with a title_key equal to its own existing title_key must not 409."""
    task_id = await create_task("solo")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"title": "  SOLO  ", "description": "d", "status": "in_progress", "priority": 4},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "SOLO"
    # Follow-up GET confirms persistence.
    fetched = await client.get(f"/v1/tasks/{task_id}")
    assert fetched.json()["title"] == "SOLO"


async def test_put_omitting_description_nulls_the_column(client: AsyncClient, create_task: CreateTask) -> None:
    """PUT is replace, not merge — omitting ``description`` from the body clears the row."""
    task_id = await create_task("with-desc")
    seed = await client.patch(f"/v1/tasks/{task_id}", json={"description": "before"})
    assert seed.json()["description"] == "before"

    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"title": "with-desc", "status": "new", "priority": 3},
    )
    assert r.status_code == 200, r.text
    assert r.json()["description"] is None
    fetched = await client.get(f"/v1/tasks/{task_id}")
    assert fetched.json()["description"] is None


async def test_put_title_collision_returns_409(client: AsyncClient, create_task: CreateTask) -> None:
    await create_task("first")
    second = await create_task("second")
    r = await client.put(
        f"/v1/tasks/{second}",
        json={"title": "  FIRST  ", "priority": 1},
    )
    assert_error(r, 409, ErrorCode.DUPLICATE_TASK)


async def test_put_missing_required_field_returns_422(client: AsyncClient, create_task: CreateTask) -> None:
    task_id = await create_task("x")
    r = await client.put(f"/v1/tasks/{task_id}", json={"title": "y"})
    assert_error(r, 422, ErrorCode.VALIDATION_ERROR)


async def test_put_rejects_server_owned_id(client: AsyncClient, create_task: CreateTask) -> None:
    task_id = await create_task("x")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"id": 1, "title": "y", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "id"})


async def test_put_rejects_server_owned_created_at(client: AsyncClient, create_task: CreateTask) -> None:
    task_id = await create_task("x")
    r = await client.put(
        f"/v1/tasks/{task_id}",
        json={"created_at": "2026-01-01T00:00:00Z", "title": "y", "priority": 1},
    )
    assert_error(r, 422, ErrorCode.READ_ONLY_FIELD, details={"field": "created_at"})
