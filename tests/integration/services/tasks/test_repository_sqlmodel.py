"""Direct SQLModel repository smoke tests (no HTTP)."""

from collections.abc import Iterator

import pytest
from app.core.constants import OrderDirection
from app.core.database import engine
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from sqlmodel import Session


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def test_add_then_get_round_trip(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    created = repo.add(title="alpha", description=None, status=Status.NEW, priority=3)
    assert created.id is not None
    fetched = repo.get(created.id)
    assert fetched.title == "alpha"
    assert fetched.title_key == "alpha"


def test_get_unknown_id_raises_task_not_found(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    with pytest.raises(TaskNotFoundError) as exc:
        repo.get(424242)
    assert exc.value.details == {"id": 424242}


def test_duplicate_title_key_raises_duplicate(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    repo.add(title="Same", description=None, status=Status.NEW, priority=1)
    with pytest.raises(DuplicateTaskError):
        repo.add(title="  SAME  ", description=None, status=Status.NEW, priority=1)


def test_list_orders_by_priority_then_created_at(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    a = repo.add(title="a", description=None, status=Status.NEW, priority=5)
    b = repo.add(title="b", description=None, status=Status.NEW, priority=1)
    c = repo.add(title="c", description=None, status=Status.NEW, priority=5)

    items_desc, total = repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.DESC,
        limit=10,
        offset=0,
    )
    assert total == 3
    # Priority 5 first; among ties, oldest created first.
    assert [t.id for t in items_desc] == [a.id, c.id, b.id]

    items_asc, _ = repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=10,
        offset=0,
    )
    assert [t.id for t in items_asc] == [b.id, a.id, c.id]


def test_list_filter_by_status(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    repo.add(title="a", description=None, status=Status.NEW, priority=1)
    repo.add(title="b", description=None, status=Status.COMPLETED, priority=2)
    items, total = repo.list(
        statuses=[Status.COMPLETED],
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.DESC,
        limit=10,
        offset=0,
    )
    assert total == 1
    assert items[0].title == "b"


def test_delete_returns_snapshot_and_removes(session: Session) -> None:
    repo = SQLModelTaskRepository(session)
    created = repo.add(title="bye", description=None, status=Status.NEW, priority=1)
    assert created.id is not None
    snapshot = repo.delete(created.id)
    assert snapshot.id == created.id
    with pytest.raises(TaskNotFoundError):
        repo.get(created.id)
