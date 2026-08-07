import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from app.core import database
from app.core.constants import OrderDirection
from app.core.outbox import OutboxRecord
from app.services.tasks.constants import TaskSortField
from app.services.tasks.domain.events import TaskCreated, TaskDeleted
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.tasks.interfaces import TaskRepositoryInterface
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

type RepoBuilder = Callable[[], AsyncSession]


def _sqlmodel_session() -> AsyncSession:
    # Via the sessionmaker so expire_on_commit=False — post-commit attribute reads
    # (e.g. ``created.id``) must not trigger a lazy refresh (async IO in sync context).
    return database.get_sessionmaker()()


REPO_BUILDERS: list[RepoBuilder] = [_sqlmodel_session]


@pytest.fixture(params=REPO_BUILDERS, ids=lambda builder: builder.__name__.lstrip("_"))
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[TaskRepositoryInterface]:
    session = request.param()
    try:
        yield SQLModelTaskRepository(session)
    finally:
        await session.close()


async def _insert(
    repo: TaskRepositoryInterface,
    *,
    title: str,
    description: str | None = None,
    status: str = "new",
    priority: int = 1,
) -> Task:
    """Build a task and persist it with no events — most cases here exercise persistence alone;
    the staging clause has its own pair of tests below."""
    task = Task.from_input(title=title, description=description, status=status, priority=priority)
    await repo.persist(task, events=[])
    return task


async def _staged(session: AsyncSession) -> list[OutboxRecord]:
    """Every outbox row visible after the repository's commit."""
    return list((await session.scalars(select(OutboxRecord))).all())


async def test_persist_stages_events_in_the_same_commit(repo: TaskRepositoryInterface, session: AsyncSession) -> None:
    """The port's staging clause: ``persist`` must durably record ``events`` alongside the row.
    Without this, an adapter that silently ignored ``events`` would pass every other test here."""
    task = Task.from_input(title="staged", description=None, status="new", priority=1)
    event = TaskCreated(task=task.snapshot())

    await repo.persist(task, events=[event])

    rows = await _staged(session)
    assert [row.event_type for row in rows] == ["TaskCreated"]
    assert rows[0].payload["id"] == str(event.id)
    assert rows[0].published_at is None  # staged pending — the relay, not the write, delivers


async def test_remove_stages_events_in_the_same_commit(repo: TaskRepositoryInterface, session: AsyncSession) -> None:
    """The delete half of the same clause — the row is gone, its event is not."""
    created = await _insert(repo, title="doomed")

    event = TaskDeleted(task=created.snapshot())
    await repo.remove(created, events=[event])

    rows = await _staged(session)
    assert [row.event_type for row in rows] == ["TaskDeleted"]
    assert rows[0].payload["id"] == str(event.id)
    with pytest.raises(TaskNotFoundError):
        await repo.get(created.id)


async def test_persist_then_get_round_trip(repo: TaskRepositoryInterface) -> None:
    created = await _insert(repo, title="  Alpha  ", description="d", status="in_progress", priority=3)
    fetched = await repo.get(created.id)
    assert fetched.id == created.id
    assert fetched.title == "Alpha"
    assert fetched.title_key == "alpha"
    assert fetched.description == "d"
    assert fetched.status == "in_progress"
    assert fetched.priority == 3
    assert fetched.created_at is not None


async def test_get_missing_raises_task_not_found(repo: TaskRepositoryInterface) -> None:
    missing = uuid.uuid4()
    with pytest.raises(TaskNotFoundError) as exc:
        await repo.get(missing)
    assert exc.value.details == {"id": str(missing)}


async def test_duplicate_title_raises_duplicate_task_with_normalized_title(
    repo: TaskRepositoryInterface,
) -> None:
    await _insert(repo, title="beta")
    with pytest.raises(DuplicateTaskError) as exc:
        await _insert(repo, title=" BETA ")
    # At the repo boundary ``details.title`` is the stored (normalised) title — the service
    # layer re-raises with the caller's verbatim input for the client-facing envelope.
    assert exc.value.details == {"title": "BETA"}


async def test_list_filters_by_status_and_sorts_desc(repo: TaskRepositoryInterface) -> None:
    await _insert(repo, title="a", status="new", priority=1)
    await _insert(repo, title="b", status="new", priority=5)
    await _insert(repo, title="c", status="completed", priority=3)
    items, total = await repo.list(
        statuses=["new"],
        task_ids=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.DESC,
        limit=10,
        offset=0,
    )
    assert total == 2
    assert [t.title for t in items] == ["b", "a"]


async def test_list_sort_asc_reverses_order(repo: TaskRepositoryInterface) -> None:
    await _insert(repo, title="a", status="new", priority=1)
    await _insert(repo, title="b", status="new", priority=5)
    items, _ = await repo.list(
        statuses=None,
        task_ids=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=10,
        offset=0,
    )
    assert [t.title for t in items] == ["a", "b"]


async def test_list_pagination_limit_and_offset(repo: TaskRepositoryInterface) -> None:
    for i, title in enumerate(["a", "b", "c", "d"], start=1):
        await _insert(repo, title=title, status="new", priority=i)
    page, total = await repo.list(
        statuses=None,
        task_ids=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=2,
        offset=1,
    )
    assert total == 4
    assert [t.title for t in page] == ["b", "c"]


async def test_persist_updates_all_mutable_fields(repo: TaskRepositoryInterface) -> None:
    created = await _insert(repo, title="orig", description="d1", status="new", priority=1)
    created.apply_replace(title="updated", description="d2", status="in_progress", priority=4)
    await repo.persist(created, events=[])
    replaced = await repo.get(created.id)
    assert replaced.title == "updated"
    assert replaced.description == "d2"
    assert replaced.status == "in_progress"
    assert replaced.priority == 4


async def test_persist_applies_partial_update(repo: TaskRepositoryInterface) -> None:
    created = await _insert(repo, title="x", status="new", priority=2)
    created.apply_patch({"priority": 5})
    await repo.persist(created, events=[])
    patched = await repo.get(created.id)
    assert patched.priority == 5
    assert patched.title == "x"


async def test_persist_title_renormalizes_title_key(repo: TaskRepositoryInterface) -> None:
    created = await _insert(repo, title="orig", status="new", priority=2)
    created.apply_patch({"title": " FRESH "})
    await repo.persist(created, events=[])
    patched = await repo.get(created.id)
    assert patched.title == "FRESH"
    assert patched.title_key == "fresh"


async def test_persist_title_to_existing_other_row_raises_duplicate(
    repo: TaskRepositoryInterface,
) -> None:
    await _insert(repo, title="first", status="new", priority=1)
    second = await _insert(repo, title="second", status="new", priority=1)
    second.apply_patch({"title": " FIRST "})
    with pytest.raises(DuplicateTaskError):
        await repo.persist(second, events=[])


async def test_persist_self_title_succeeds(repo: TaskRepositoryInterface) -> None:
    """PUT-replace with the same title_key on the same row must not 409 against itself."""
    created = await _insert(repo, title="solo", description="d1", status="new", priority=1)
    created.apply_replace(title="SOLO", description="d2", status="in_progress", priority=4)
    await repo.persist(created, events=[])
    replaced = await repo.get(created.id)
    assert replaced.title == "SOLO"
    assert replaced.title_key == "solo"
    assert replaced.description == "d2"
    assert replaced.status == "in_progress"


async def test_remove_deletes_the_row(repo: TaskRepositoryInterface) -> None:
    created = await _insert(repo, title="d", status="new", priority=2)
    await repo.remove(created, events=[])
    with pytest.raises(TaskNotFoundError):
        await repo.get(created.id)


async def test_count_by_status_groups_with_plain_string_keys(repo: TaskRepositoryInterface) -> None:
    await _insert(repo, title="a", status="new", priority=1)
    await _insert(repo, title="b", status="new", priority=2)
    await _insert(repo, title="c", status="completed", priority=3)

    counts = await repo.count_by_status()

    assert counts == {"new": 2, "completed": 1}
    assert all(type(key) is str for key in counts)  # wire keys, not enum members


def test_task_sort_field_values_match_task_columns() -> None:
    # repository.list() uses TaskSortField.value as a getattr name on Task.
    for member in TaskSortField:
        assert hasattr(Task, member.value), f"{member.name}={member.value!r} has no matching Task attribute"
