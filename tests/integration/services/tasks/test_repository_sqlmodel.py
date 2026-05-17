"""SQLite-specific repository tests not covered by the parametrised contract suite."""

from collections.abc import Iterator

import pytest
from app.core.constants import OrderDirection
from app.core.database import engine
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from sqlmodel import Session


@pytest.fixture
def session() -> Iterator[Session]:
    with Session(engine) as s:
        yield s


def test_list_orders_by_priority_then_created_at(session: Session) -> None:
    """Tiebreaker contract: equal priorities resolve by ``created_at`` ascending (FRD §3.3)."""
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
