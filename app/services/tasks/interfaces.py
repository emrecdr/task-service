from abc import ABC, abstractmethod
from typing import Any

from app.core.constants import OrderDirection
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.domain.models import Task


class TaskRepositoryInterface(ABC):
    """``replace`` and ``patch`` return ``(snapshot_before, row_after)`` from one fetch."""

    @abstractmethod
    def add(
        self,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> Task: ...

    @abstractmethod
    def get(self, task_id: int) -> Task: ...

    @abstractmethod
    def list(
        self,
        *,
        statuses: list[Status] | None,
        order_by: TaskSortField,
        order_dir: OrderDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]: ...

    @abstractmethod
    def replace(
        self,
        task_id: int,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> tuple[Task, Task]: ...

    @abstractmethod
    def patch(self, task_id: int, **fields: Any) -> tuple[Task, Task]: ...

    @abstractmethod
    def delete(self, task_id: int) -> Task: ...
