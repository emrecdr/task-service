"""Repository contract for the tasks feature.

ABC + ``@abstractmethod`` is preferred over ``Protocol`` here so that any
implementation forgetting a method fails at *instantiation* time with a clear
``TypeError``, rather than at first call with a confusing ``AttributeError``.
"""

from abc import ABC, abstractmethod
from typing import Final

from app.core.constants import OrderDirection
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.domain.models import Task

# Fields the repository accepts for patch() and the service uses for change-detection.
MUTABLE_FIELDS: Final[frozenset[str]] = frozenset({"title", "description", "status", "priority"})


class TaskRepositoryInterface(ABC):
    """``replace`` and ``patch`` return ``(pre_mutation_snapshot, updated_row)``
    from a single fetch so the service can fire change-detection events without
    a second read.
    """

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
    def patch(self, task_id: int, **fields: object) -> tuple[Task, Task]: ...

    @abstractmethod
    def delete(self, task_id: int) -> Task: ...
