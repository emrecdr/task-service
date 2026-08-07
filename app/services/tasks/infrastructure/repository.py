import uuid
from collections.abc import Sequence

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.constants import OrderDirection
from app.core.event_bus import Event
from app.core.outbox import stage_events
from app.services.tasks.constants import TITLE_KEY_CONSTRAINT, TaskSortField
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface


def _is_title_key_violation(err: IntegrityError) -> bool:
    # Match asyncpg's ``UniqueViolationError.constraint_name`` against the named constraint
    # (``Task.__table_args__``) — a dialect-stable check, not error-message parsing.
    cause = err.orig.__cause__ if err.orig is not None else None
    constraint = getattr(cause, "constraint_name", None)
    if constraint is not None:
        return constraint == TITLE_KEY_CONSTRAINT
    # Fallback for drivers that don't expose the constraint name on the exception.
    return TITLE_KEY_CONSTRAINT in str(err.orig)


class SQLModelTaskRepository(TaskRepositoryInterface):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist(self, task: Task, *, events: Sequence[Event]) -> None:
        # ``add`` stages an INSERT for a new task and is a no-op for an already-tracked one
        # (a fetched-and-mutated row) — so one method covers create and update. The outbox
        # rows and the row change share this single commit, giving all-or-nothing atomicity.
        self._session.add(task)
        stage_events(self._session, events)
        await self._commit_or_translate(task.title)

    async def stage(self, task: Task) -> None:
        self._session.add(task)
        try:
            await self._session.flush()
        except IntegrityError as err:
            await self._session.rollback()
            if _is_title_key_violation(err):
                raise DuplicateTaskError(details={"title": task.title}, original_error=err) from err
            raise

    async def remove(self, task: Task, *, events: Sequence[Event]) -> None:
        await self._session.delete(task)
        stage_events(self._session, events)
        await self._session.commit()

    async def get(self, task_id: uuid.UUID) -> Task:
        task = await self._session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(details={"id": str(task_id)})
        return task

    async def list(
        self,
        *,
        statuses: list[str] | None,
        task_ids: set[uuid.UUID] | None,
        order_by: TaskSortField,
        order_dir: OrderDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        base = select(Task)
        count_stmt = select(func.count()).select_from(Task)
        if statuses:
            base = base.where(col(Task.status).in_(statuses))
            count_stmt = count_stmt.where(col(Task.status).in_(statuses))
        if task_ids is not None:
            # The tag filter, already resolved to task IDs by the service. ``None`` means no
            # tag filter was asked for; an empty set means one was and nothing matched, so it
            # must still constrain the query rather than being treated as absent.
            base = base.where(col(Task.id).in_(task_ids))
            count_stmt = count_stmt.where(col(Task.id).in_(task_ids))

        # ``order_by`` is a StrEnum whose value IS the column attribute name.
        sort_col = col(getattr(Task, order_by))
        ordered = sort_col.desc() if order_dir is OrderDirection.DESC else sort_col.asc()
        # ``id`` (uuid7, time-ordered) is the final unique tiebreak so paging stays stable
        # when ``priority`` and ``created_at`` both tie (e.g. bulk creates in the same tick).
        items_stmt = base.order_by(ordered, col(Task.created_at).asc(), col(Task.id).asc()).offset(offset).limit(limit)

        items = list((await self._session.scalars(items_stmt)).all())
        total = int(await self._session.scalar(count_stmt) or 0)
        return items, total

    async def count_by_status(self) -> dict[str, int]:
        stmt = select(col(Task.status), func.count()).group_by(col(Task.status))
        rows = (await self._session.execute(stmt)).all()
        return {str(row[0]): int(row[1]) for row in rows}

    async def _commit_or_translate(self, title: str) -> None:
        """Commit; translate a ``title_key`` UNIQUE violation into ``DuplicateTaskError``."""
        try:
            await self._session.commit()
        except IntegrityError as err:
            await self._session.rollback()
            if _is_title_key_violation(err):
                raise DuplicateTaskError(details={"title": title}, original_error=err) from err
            raise
