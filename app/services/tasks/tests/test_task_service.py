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
        task = self.get(task_id)
        snapshot = task.snapshot()
        del self._rows[task_id]
        return snapshot


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
    async def test_fires_task_created_carrying_full_row(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(
            title="  Alpha  ",
            description="d",
            status=Status.IN_PROGRESS,
            priority=4,
            background_tasks=bt,
        )
        assert [type(e) for e in bus.published] == [TaskCreated]
        event = bus.published[0]
        assert isinstance(event, TaskCreated)
        assert event.task.id == 1
        assert event.task.title == "Alpha"
        assert event.task.title_key == "alpha"
        assert event.task.description == "d"
        assert event.task.status is Status.IN_PROGRESS
        assert event.task.priority == 4


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

    async def test_status_to_in_progress_fires_updated_then_status_changed(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": Status.IN_PROGRESS}, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.previous.status is Status.NEW
        assert updated.task.status is Status.IN_PROGRESS
        assert updated.changed_fields == ["status"]
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status is Status.NEW
        assert status_changed.to_status is Status.IN_PROGRESS
        assert status_changed.task.id == 1

    async def test_status_to_completed_fires_three_events_in_order(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": Status.COMPLETED}, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        updated, status_changed, completed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["status"]
        assert updated.previous.status is Status.NEW
        assert updated.task.status is Status.COMPLETED
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status is Status.NEW
        assert status_changed.to_status is Status.COMPLETED
        assert isinstance(completed, TaskCompleted)
        assert completed.task.id == 1
        assert completed.task.status is Status.COMPLETED

    async def test_non_status_change_fires_only_task_updated_with_field_list(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"priority": 5}, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated]
        updated = bus.published[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["priority"]
        assert updated.previous.priority == 1
        assert updated.task.priority == 5

    async def test_multi_field_change_lists_fields_in_canonical_order(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        # MUTABLE_FIELDS order = ("title", "description", "status", "priority").
        # changed_fields must follow this order even if input dict shuffles them.
        await service.patch(
            1,
            fields={"priority": 5, "title": "renamed", "description": "d"},
            background_tasks=bt,
        )
        updated = bus.published[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["title", "description", "priority"]

    async def test_unknown_id_raises_task_not_found(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.patch(999, fields={"priority": 5}, background_tasks=bt)
        assert bus.published == []


class TestReplace:
    async def test_no_actual_change_does_not_fire_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description="d", status=Status.NEW, priority=3, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description="d", status=Status.NEW, priority=3, background_tasks=bt)
        assert bus.published == []

    async def test_full_replace_fires_updated_with_all_changed_fields(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="orig", description="d1", status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.replace(
            1,
            title="renamed",
            description="d2",
            status=Status.IN_PROGRESS,
            priority=5,
            background_tasks=bt,
        )
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["title", "description", "status", "priority"]
        assert updated.previous.title == "orig"
        assert updated.previous.description == "d1"
        assert updated.previous.status is Status.NEW
        assert updated.previous.priority == 1
        assert updated.task.title == "renamed"
        assert updated.task.description == "d2"
        assert updated.task.status is Status.IN_PROGRESS
        assert updated.task.priority == 5
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status is Status.NEW
        assert status_changed.to_status is Status.IN_PROGRESS

    async def test_replace_to_completed_fires_all_three_events_in_order(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=3, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description=None, status=Status.COMPLETED, priority=3, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        completed = bus.published[2]
        assert isinstance(completed, TaskCompleted)
        assert completed.task.status is Status.COMPLETED

    async def test_replace_non_status_field_only_fires_task_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description=None, status=Status.NEW, priority=5, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated]
        updated = bus.published[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["priority"]

    async def test_unknown_id_raises_task_not_found(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.replace(999, title="x", description=None, status=Status.NEW, priority=1, background_tasks=bt)
        assert bus.published == []


class TestDelete:
    async def test_fires_task_deleted_with_detached_snapshot(
        self, service: TaskService, repo: FakeRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(
            title="alpha",
            description="d",
            status=Status.IN_PROGRESS,
            priority=4,
            background_tasks=bt,
        )
        bus.published.clear()
        await service.delete(1, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskDeleted]
        event = bus.published[0]
        assert isinstance(event, TaskDeleted)
        assert event.task.id == 1
        assert event.task.title == "alpha"
        assert event.task.description == "d"
        assert event.task.status is Status.IN_PROGRESS
        assert event.task.priority == 4
        # Snapshot must survive row deletion — the row is gone but the event still carries its data.
        assert 1 not in repo._rows

    async def test_unknown_id_raises_task_not_found(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.delete(999, background_tasks=bt)
        assert bus.published == []
