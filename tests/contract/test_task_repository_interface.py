from collections.abc import Callable, Iterator

import pytest
from app.core.constants import OrderDirection
from app.core.database import engine
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from app.services.tasks.interfaces import TaskRepositoryInterface
from sqlmodel import Session

type RepoFactory = Callable[[], tuple[TaskRepositoryInterface, Callable[[], None]]]


def _sqlmodel_repo() -> tuple[TaskRepositoryInterface, Callable[[], None]]:
    session = Session(engine)
    return SQLModelTaskRepository(session), session.close


REPO_BUILDERS: list[RepoFactory] = [_sqlmodel_repo]


@pytest.fixture(params=REPO_BUILDERS, ids=lambda factory: factory.__name__.lstrip("_"))
def repo(request: pytest.FixtureRequest) -> Iterator[TaskRepositoryInterface]:
    instance, teardown = request.param()
    try:
        yield instance
    finally:
        teardown()


def test_add_then_get_round_trip(repo: TaskRepositoryInterface) -> None:
    created = repo.add(title="alpha", description=None, status=Status.NEW, priority=3)
    assert created.id is not None
    fetched = repo.get(created.id)
    assert fetched.id == created.id
    assert fetched.title == "alpha"


def test_get_missing_raises_task_not_found(repo: TaskRepositoryInterface) -> None:
    with pytest.raises(TaskNotFoundError) as exc:
        repo.get(9999)
    assert exc.value.details == {"id": 9999}


def test_duplicate_title_raises_duplicate_task(repo: TaskRepositoryInterface) -> None:
    repo.add(title="beta", description=None, status=Status.NEW, priority=1)
    with pytest.raises(DuplicateTaskError):
        repo.add(title=" BETA ", description=None, status=Status.NEW, priority=1)


def test_list_filters_by_status_and_sorts_desc(repo: TaskRepositoryInterface) -> None:
    repo.add(title="a", description=None, status=Status.NEW, priority=1)
    repo.add(title="b", description=None, status=Status.NEW, priority=5)
    repo.add(title="c", description=None, status=Status.COMPLETED, priority=3)
    items, total = repo.list(
        statuses=[Status.NEW],
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.DESC,
        limit=10,
        offset=0,
    )
    assert total == 2
    assert [t.title for t in items] == ["b", "a"]


def test_list_sort_asc_reverses_order(repo: TaskRepositoryInterface) -> None:
    repo.add(title="a", description=None, status=Status.NEW, priority=1)
    repo.add(title="b", description=None, status=Status.NEW, priority=5)
    items, _ = repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=10,
        offset=0,
    )
    assert [t.title for t in items] == ["a", "b"]


def test_list_pagination_limit_and_offset(repo: TaskRepositoryInterface) -> None:
    for i, title in enumerate(["a", "b", "c", "d"], start=1):
        repo.add(title=title, description=None, status=Status.NEW, priority=i)
    page, total = repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=2,
        offset=1,
    )
    assert total == 4
    assert [t.title for t in page] == ["b", "c"]


def test_replace_updates_all_mutable_fields(repo: TaskRepositoryInterface) -> None:
    created = repo.add(title="orig", description="d1", status=Status.NEW, priority=1)
    assert created.id is not None
    previous, replaced = repo.replace(
        created.id,
        title="updated",
        description="d2",
        status=Status.IN_PROGRESS,
        priority=4,
    )
    assert previous.title == "orig"
    assert previous.description == "d1"
    assert previous.status is Status.NEW
    assert previous.priority == 1
    assert replaced.title == "updated"
    assert replaced.description == "d2"
    assert replaced.status is Status.IN_PROGRESS
    assert replaced.priority == 4


def test_patch_applies_partial_update(repo: TaskRepositoryInterface) -> None:
    created = repo.add(title="x", description=None, status=Status.NEW, priority=2)
    assert created.id is not None
    previous, patched = repo.patch(created.id, priority=5)
    assert previous.priority == 2
    assert previous.title == "x"
    assert patched.priority == 5
    assert patched.title == "x"


def test_delete_returns_snapshot_and_removes(repo: TaskRepositoryInterface) -> None:
    created = repo.add(title="d", description=None, status=Status.NEW, priority=2)
    assert created.id is not None
    snapshot = repo.delete(created.id)
    assert snapshot.id == created.id
    assert snapshot.title == "d"
    with pytest.raises(TaskNotFoundError):
        repo.get(created.id)


def test_task_sort_field_values_match_task_columns() -> None:
    # repository.list() uses TaskSortField.value as a getattr name on Task.
    for member in TaskSortField:
        assert hasattr(Task, member.value), f"{member.name}={member.value!r} has no matching Task attribute"
