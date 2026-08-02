"""Repository ordering tests not covered by the parametrised contract suite."""

from collections.abc import AsyncIterator

import pytest
from app.core import database
from app.core.constants import OrderDirection
from app.services.tasks.constants import TaskSortField
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with database.session_factory() as s:
        yield s


async def test_list_orders_by_priority_then_created_at(session: AsyncSession) -> None:
    """Tiebreaker contract: equal priorities resolve by ``created_at`` ascending (FRD §3.3)."""
    repo = SQLModelTaskRepository(session)
    a = await repo.add(title="a", description=None, status="new", priority=5)
    b = await repo.add(title="b", description=None, status="new", priority=1)
    c = await repo.add(title="c", description=None, status="new", priority=5)

    items_desc, total = await repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.DESC,
        limit=10,
        offset=0,
    )
    assert total == 3
    assert [t.id for t in items_desc] == [a.id, c.id, b.id]

    items_asc, _ = await repo.list(
        statuses=None,
        order_by=TaskSortField.PRIORITY,
        order_dir=OrderDirection.ASC,
        limit=10,
        offset=0,
    )
    assert [t.id for t in items_asc] == [b.id, a.id, c.id]
