"""SQLModel-backed implementation of :class:`TaskRepositoryInterface`.

Translates SQLite ``IntegrityError`` from the UNIQUE constraint on
``title_key`` into :class:`DuplicateTaskError` (FRD §3.1 / §4). The check
matches against ``"title_key"`` in the driver error string — fragile across
backends but acceptable at Phase 1 single-driver scope.
"""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status
from app.services.tasks.errors import DuplicateTaskError, TaskNotFoundError
from app.services.tasks.interfaces import Sort, TaskRepositoryInterface


_MUTABLE_FIELDS = frozenset({"title", "description", "status", "priority"})


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
        self._session.refresh(task)
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
        sort: Sort,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        base = select(Task)
        count_stmt = select(func.count()).select_from(Task)
        if statuses:
            base = base.where(Task.status.in_(statuses))  # type: ignore[attr-defined]
            count_stmt = count_stmt.where(Task.status.in_(statuses))  # type: ignore[attr-defined]

        order_col = (
            Task.priority.desc()  # type: ignore[attr-defined]
            if sort == "priority_desc"
            else Task.priority.asc()  # type: ignore[attr-defined]
        )
        items_stmt = (
            base.order_by(order_col, Task.created_at.asc())  # type: ignore[attr-defined]
            .offset(offset)
            .limit(limit)
        )

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
    ) -> Task:
        task = self.get(task_id)
        task.title, task.title_key = Task.clean_title(title)
        task.description = description
        task.status = status
        task.priority = priority
        self._commit_or_translate(title)
        self._session.refresh(task)
        return task

    def patch(self, task_id: int, **fields: Any) -> Task:
        unknown = set(fields) - _MUTABLE_FIELDS
        if unknown:
            raise ValueError(f"unknown patch fields: {sorted(unknown)}")
        task = self.get(task_id)
        if "title" in fields:
            task.title, task.title_key = Task.clean_title(fields.pop("title"))
        for field, value in fields.items():
            setattr(task, field, value)
        self._commit_or_translate(task.title)
        self._session.refresh(task)
        return task

    def delete(self, task_id: int) -> Task:
        task = self.get(task_id)
        snapshot = Task.model_validate(task.model_dump())
        self._session.delete(task)
        self._session.commit()
        return snapshot

    def _commit_or_translate(self, title: str) -> None:
        """Commit; translate the title_key UNIQUE violation into ``DuplicateTaskError``."""
        try:
            self._session.commit()
        except IntegrityError as err:
            self._session.rollback()
            if "title_key" in str(err.orig):
                raise DuplicateTaskError(details={"title": title}) from err
            raise
