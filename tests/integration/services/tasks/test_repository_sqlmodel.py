"""Repository ordering tests not covered by the parametrised contract suite."""

from app.core.constants import OrderDirection
from app.services.tasks.constants import TaskSortField
from app.services.tasks.domain.models import Task
from app.services.tasks.infrastructure.repository import SQLModelTaskRepository
from sqlalchemy.ext.asyncio import AsyncSession


async def _add(repo: SQLModelTaskRepository, title: str, priority: int) -> Task:
    task = Task.from_input(title=title, description=None, status="new", priority=priority)
    await repo.persist(task, events=[])
    return task


async def test_list_orders_by_priority_then_created_at(session: AsyncSession) -> None:
    """Tiebreaker contract: equal priorities resolve by ``created_at`` ascending (FRD §3.3)."""
    repo = SQLModelTaskRepository(session)
    a = await _add(repo, "a", 5)
    b = await _add(repo, "b", 1)
    c = await _add(repo, "c", 5)

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
