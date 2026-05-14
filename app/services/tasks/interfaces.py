"""Repository contract for the tasks feature.

ABC + ``@abstractmethod`` is preferred over ``Protocol`` here so that any
implementation forgetting a method fails at *instantiation* time with a clear
``TypeError``, rather than at first call with a confusing ``AttributeError``.
"""

from abc import ABC, abstractmethod
from typing import Final, Literal

from app.services.tasks.domain.models import Task
from app.services.tasks.enums import Status

Sort = Literal["priority_asc", "priority_desc"]

# Fields the repository accepts for patch() and the service uses for change-detection.
MUTABLE_FIELDS: Final[frozenset[str]] = frozenset({"title", "description", "status", "priority"})


class TaskRepositoryInterface(ABC):
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
        sort: Sort,
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
    ) -> Task: ...

    @abstractmethod
    def patch(self, task_id: int, **fields: object) -> Task: ...

    @abstractmethod
    def delete(self, task_id: int) -> Task: ...
