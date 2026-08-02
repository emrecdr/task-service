import uuid
from abc import ABC, abstractmethod
from typing import Any

from app.core.constants import OrderDirection
from app.services.tasks.constants import TaskSortField
from app.services.tasks.domain.models import Task


class TaskRepositoryInterface(ABC):
    """``replace`` and ``patch`` return ``(snapshot_before, row_after)`` from one fetch."""

    @abstractmethod
    async def add(
        self,
        *,
        title: str,
        description: str | None,
        status: str,
        priority: int,
    ) -> Task: ...

    @abstractmethod
    async def get(self, task_id: uuid.UUID) -> Task: ...

    @abstractmethod
    async def list(
        self,
        *,
        statuses: list[str] | None,
        order_by: TaskSortField,
        order_dir: OrderDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]: ...

    @abstractmethod
    async def replace(
        self,
        task_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        status: str,
        priority: int,
    ) -> tuple[Task, Task]: ...

    @abstractmethod
    async def patch(self, task_id: uuid.UUID, **fields: Any) -> tuple[Task, Task]: ...

    @abstractmethod
    async def delete(self, task_id: uuid.UUID) -> Task: ...

    @abstractmethod
    async def count_by_status(self) -> dict[str, int]: ...
