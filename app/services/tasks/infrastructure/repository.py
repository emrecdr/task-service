"""SQLModel-backed implementation of :class:`TaskRepositoryInterface`."""

from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, col

from app.core.constants import OrderDirection
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface

# Fragment of the SQLite UNIQUE-violation message identifying the ``title_key`` index.
_TITLE_KEY_INDEX_FRAGMENT: Final[str] = "title_key"


class SQLModelTaskRepository(TaskRepositoryInterface):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> Task:
        task = Task.from_input(
            title=title,
            description=description,
            status=status,
            priority=priority,
        )
        self._session.add(task)
        self._commit_or_translate(title)
        return task

    def get(self, task_id: int) -> Task:
        task = self._session.get(Task, task_id)
        if task is None:
            raise TaskNotFoundError(details={"id": task_id})
        return task

    def list(
        self,
        *,
        statuses: list[Status] | None,
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

        # ``order_by`` is a StrEnum whose value IS the column attribute name.
        sort_col = col(getattr(Task, order_by))
        ordered = sort_col.desc() if order_dir is OrderDirection.DESC else sort_col.asc()
        items_stmt = base.order_by(ordered, col(Task.created_at).asc()).offset(offset).limit(limit)

        items = list(self._session.scalars(items_stmt).all())
        total = int(self._session.scalar(count_stmt) or 0)
        return items, total

    def replace(
        self,
        task_id: int,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> tuple[Task, Task]:
        task = self.get(task_id)
        previous = task.snapshot()
        task.apply_replace(title=title, description=description, status=status, priority=priority)
        self._commit_or_translate(title)
        return previous, task

    def patch(self, task_id: int, **fields: Any) -> tuple[Task, Task]:
        task = self.get(task_id)
        previous = task.snapshot()
        task.apply_patch(fields)
        self._commit_or_translate(task.title)
        return previous, task

    def delete(self, task_id: int) -> Task:
        task = self.get(task_id)
        snapshot = task.snapshot()
        self._session.delete(task)
        self._session.commit()
        return snapshot

    def _commit_or_translate(self, title: str) -> None:
        """Commit; translate a ``title_key`` UNIQUE violation into ``DuplicateTaskError``."""
        try:
            self._session.commit()
        except IntegrityError as err:
            self._session.rollback()
            if _TITLE_KEY_INDEX_FRAGMENT in str(err.orig):
                raise DuplicateTaskError(details={"title": title}, original_error=err) from err
            raise
