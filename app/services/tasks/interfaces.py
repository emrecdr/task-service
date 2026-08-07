import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence

from app.core.constants import OrderDirection
from app.core.event_bus import Event
from app.services.tasks.constants import TaskSortField
from app.services.tasks.domain.models import Task


class TaskRepositoryInterface(ABC):
    """A persistence port. Writes are transactional-outbox aware: ``persist``/``remove`` stage
    the given ``events`` into the outbox and commit them **atomically** with the row change, so
    a task and its events are all-or-nothing. Domain construction/mutation and the decision of
    *which* events to emit stay in the service — the repo only persists what it is handed."""

    @abstractmethod
    async def persist(self, task: Task, *, events: Sequence[Event]) -> None:
        """Insert or update ``task`` and stage ``events``, in one commit (duplicate ``title_key``
        → ``DuplicateTaskError``)."""

    @abstractmethod
    async def stage(self, task: Task) -> None:
        """Insert the row into the open transaction without committing.

        Exists so a caller can make a *new* task addressable mid-transaction — the tags join
        has a foreign key to ``tasks``, and SQLAlchemy builds its flush order from
        ``relationship()`` declarations, which these tables deliberately do not have. Without
        an explicit flush the join rows can be inserted first and violate the constraint.
        """

    @abstractmethod
    async def get(self, task_id: uuid.UUID) -> Task: ...

    @abstractmethod
    async def list(
        self,
        *,
        statuses: list[str] | None,
        task_ids: set[uuid.UUID] | None,
        order_by: TaskSortField,
        order_dir: OrderDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]: ...

    @abstractmethod
    async def remove(self, task: Task, *, events: Sequence[Event]) -> None:
        """Delete ``task`` and stage ``events``, in one commit."""

    @abstractmethod
    async def count_by_status(self) -> dict[str, int]: ...
