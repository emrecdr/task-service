"""Service-layer unit tests for event-firing rules — fake repo + recording bus."""

from typing import Any

import pytest
from fastapi import BackgroundTasks

from app.core.constants import OrderDirection
from app.core.event_bus import Event, EventBus
from app.services.tasks.application.service import TaskService
from app.services.tasks.constants import Status, TaskSortField
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import EmptyUpdateError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface


class FakeRepo(TaskRepositoryInterface):
    def __init__(self) -> None:
        self._rows: dict[int, Task] = {}
        self._next_id = 1

    def add(
        self,
        *,
        title: str,
        description: str | None,
        status: Status,
        priority: int,
    ) -> Task:
        task = Task.from_input(title=title, description=description, status=status, priority=priority)
        task.id = self._next_id
        self._rows[task.id] = task
        self._next_id += 1
        return task

    def get(self, task_id: int) -> Task:
        try:
            return self._rows[task_id]
        except KeyError as err:
            raise TaskNotFoundError(details={"id": task_id}) from err

    def list(
        self,
        *,
        statuses: list[Status] | None,
        order_by: TaskSortField,
        order_dir: OrderDirection,
        limit: int,
        offset: int,
    ) -> tuple[list[Task], int]:
        rows = list(self._rows.values())
        return rows[offset : offset + limit], len(rows)

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
        return previous, task

    def patch(self, task_id: int, **fields: Any) -> tuple[Task, Task]:
        task = self.get(task_id)
        previous = task.snapshot()
        task.apply_patch(fields)
        return previous, task

    def delete(self, task_id: int) -> Task:
        return self._rows.pop(task_id).snapshot()


class RecordingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[Event] = []

    def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        self.published.append(event)


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def bus() -> RecordingBus:
    return RecordingBus()


@pytest.fixture
def service(repo: FakeRepo, bus: RecordingBus) -> TaskService:
    return TaskService(repo=repo, events=bus)


@pytest.fixture
def bt() -> BackgroundTasks:
    return BackgroundTasks()


class TestCreate:
    async def test_create_fires_task_created(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        assert len(bus.published) == 1
        assert isinstance(bus.published[0], TaskCreated)


class TestPatch:
    async def test_empty_body_raises_empty_update(self, service: TaskService, bt: BackgroundTasks) -> None:
        with pytest.raises(EmptyUpdateError):
            await service.patch(1, fields={}, background_tasks=bt)

    async def test_no_actual_change_does_not_fire_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"priority": 1}, background_tasks=bt)
        assert bus.published == []

    async def test_status_to_in_progress_fires_updated_and_status_changed_only(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": Status.IN_PROGRESS}, background_tasks=bt)
        types = [type(e) for e in bus.published]
        assert TaskUpdated in types
        assert TaskStatusChanged in types
        assert TaskCompleted not in types

    async def test_status_to_completed_fires_all_three(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": Status.COMPLETED}, background_tasks=bt)
        types = [type(e) for e in bus.published]
        assert TaskUpdated in types
        assert TaskStatusChanged in types
        assert TaskCompleted in types

    async def test_non_status_change_fires_only_task_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"priority": 5}, background_tasks=bt)
        types = [type(e) for e in bus.published]
        assert types == [TaskUpdated]


class TestDelete:
    async def test_fires_task_deleted_with_snapshot(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.delete(1, background_tasks=bt)
        assert isinstance(bus.published[0], TaskDeleted)
        assert bus.published[0].task.id == 1
