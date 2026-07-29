"""Service-layer unit tests for event-firing and workflow-enforcement rules."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import BackgroundTasks

from app.core.constants import OrderDirection
from app.core.errors import ValidationError
from app.core.event_bus import Event, EventBus
from app.services.tasks.application.service import TaskService
from app.services.tasks.constants import TaskSortField
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import EmptyUpdateError, InvalidTransitionError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State
from app.services.workflows.interfaces import StoredWorkflow, WorkflowRepositoryInterface


def _any_to_any() -> Workflow:
    """Seed-equivalent: three states, all entries, every directed pair legal."""
    workflow = Workflow(
        states=[
            State("new", initial=True),
            State("in_progress", initial=True),
            State("completed", initial=True, meta={"completes": True}),
        ]
    )
    workflow.allow_transition("Start work", from_state="new", to_state="in_progress")
    workflow.allow_transition("Complete", from_state="new", to_state="completed")
    workflow.allow_transition("Complete", from_state="in_progress", to_state="completed")
    workflow.allow_transition("Send back", from_state="in_progress", to_state="new")
    workflow.allow_transition("Reopen", from_state="completed", to_state="new")
    workflow.allow_transition("Resume", from_state="completed", to_state="in_progress")
    return workflow


def _strict() -> Workflow:
    """Single entry, one forward path: new -> in_progress -> completed."""
    workflow = Workflow(
        states=[
            State("new", initial=True),
            State("in_progress"),
            State("completed", meta={"completes": True}),
        ]
    )
    workflow.allow_transition("Start work", from_state="new", to_state="in_progress")
    workflow.allow_transition("Finish", from_state="in_progress", to_state="completed")
    return workflow


class FakeWorkflowRepo(WorkflowRepositoryInterface):
    def __init__(self, workflow: Workflow) -> None:
        self._workflow = workflow

    def get_active(self) -> StoredWorkflow:
        return StoredWorkflow(workflow=self._workflow, version=1, created_at=datetime.now(UTC))

    def replace_active(self, workflow: Workflow) -> StoredWorkflow:  # pragma: no cover - never called
        raise AssertionError("not used")


class FakeRepo(TaskRepositoryInterface):
    def __init__(self) -> None:
        self._rows: dict[int, Task] = {}
        self._next_id = 1

    def add(
        self,
        *,
        title: str,
        description: str | None,
        status: str,
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
        statuses: list[str] | None,
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
        status: str,
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

    def count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for task in self._rows.values():
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts


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
    return TaskService(repo=repo, workflows=FakeWorkflowRepo(_any_to_any()), events=bus)


@pytest.fixture
def strict_service(repo: FakeRepo, bus: RecordingBus) -> TaskService:
    return TaskService(repo=repo, workflows=FakeWorkflowRepo(_strict()), events=bus)


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
            status="in_progress",
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
        assert event.task.status == "in_progress"
        assert event.task.priority == 4

    async def test_omitted_status_resolves_to_default_entry(
        self, strict_service: TaskService, bt: BackgroundTasks
    ) -> None:
        task = await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        assert task.status == "new"

    async def test_non_entry_status_raises_invalid_transition(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.create(
                title="a", description=None, status="completed", priority=1, background_tasks=bt
            )
        assert exc.value.details == {"from": None, "to": "completed", "allowed": ["new"]}
        assert bus.published == []

    async def test_unknown_status_raises_validation_error(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(ValidationError) as exc:
            await strict_service.create(title="a", description=None, status="ghost", priority=1, background_tasks=bt)
        assert exc.value.details == {
            "field": "status",
            "value": "ghost",
            "known_states": ["new", "in_progress", "completed"],
        }
        assert bus.published == []


class TestLegalMoves:
    async def test_returns_task_and_leaving_transitions(self, strict_service: TaskService, bt: BackgroundTasks) -> None:
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)

        task, transitions = await strict_service.legal_moves(1)

        assert task.status == "new"
        assert [(t.name, t.to_state) for t in transitions] == [("Start work", "in_progress")]

    async def test_unknown_id_raises_task_not_found(self, strict_service: TaskService) -> None:
        with pytest.raises(TaskNotFoundError):
            await strict_service.legal_moves(999)


class TestPatch:
    async def test_empty_body_raises_empty_update(self, service: TaskService, bt: BackgroundTasks) -> None:
        with pytest.raises(EmptyUpdateError):
            await service.patch(1, fields={}, background_tasks=bt)

    async def test_no_actual_change_does_not_fire_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"priority": 1}, background_tasks=bt)
        assert bus.published == []

    async def test_same_state_patch_needs_no_transition_and_fires_no_events(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        # The strict workflow has no new -> new transition; a same-state write
        # must still succeed as a no-move.
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        bus.published.clear()
        await strict_service.patch(1, fields={"status": "new"}, background_tasks=bt)
        assert bus.published == []

    async def test_illegal_move_raises_invalid_transition_with_allowed_list(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        bus.published.clear()
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.patch(1, fields={"status": "completed"}, background_tasks=bt)
        assert exc.value.details == {"from": "new", "to": "completed", "allowed": ["in_progress"]}
        assert bus.published == []

    async def test_unknown_target_state_raises_validation_error(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        bus.published.clear()
        with pytest.raises(ValidationError):
            await strict_service.patch(1, fields={"status": "ghost"}, background_tasks=bt)
        assert bus.published == []

    async def test_status_to_in_progress_fires_updated_then_status_changed(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": "in_progress"}, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.previous.status == "new"
        assert updated.task.status == "in_progress"
        assert updated.changed_fields == ["status"]
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status == "new"
        assert status_changed.to_status == "in_progress"
        assert status_changed.task.id == 1

    async def test_entering_completing_state_fires_three_events_in_order(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
        bus.published.clear()
        await service.patch(1, fields={"status": "completed"}, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        updated, status_changed, completed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["status"]
        assert updated.previous.status == "new"
        assert updated.task.status == "completed"
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status == "new"
        assert status_changed.to_status == "completed"
        assert isinstance(completed, TaskCompleted)
        assert completed.task.id == 1
        assert completed.task.status == "completed"

    async def test_entering_non_completing_state_does_not_fire_completed(
        self, repo: FakeRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        # "done" carries no completes meta — TaskCompleted must stay silent.
        workflow = Workflow(states=[State("open", initial=True), State("done")])
        workflow.allow_transition("Close", from_state="open", to_state="done")
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(workflow), events=bus)
        await service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        bus.published.clear()

        await service.patch(1, fields={"status": "done"}, background_tasks=bt)

        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged]

    async def test_non_status_change_fires_only_task_updated_with_field_list(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
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
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
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
        await service.create(title="a", description="d", status="new", priority=3, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description="d", status="new", priority=3, background_tasks=bt)
        assert bus.published == []

    async def test_omitted_status_resolves_to_default_entry_and_move_checks(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        # in_progress -> new is not a strict-workflow transition, so a PUT that
        # omits status while the task is mid-flow is a loud 409, not a silent reset.
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        await strict_service.patch(1, fields={"status": "in_progress"}, background_tasks=bt)
        bus.published.clear()
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.replace(1, title="a", description=None, status=None, priority=1, background_tasks=bt)
        assert exc.value.details == {"from": "in_progress", "to": "new", "allowed": ["completed"]}
        assert bus.published == []

    async def test_full_replace_fires_updated_with_all_changed_fields(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="orig", description="d1", status="new", priority=1, background_tasks=bt)
        bus.published.clear()
        await service.replace(
            1,
            title="renamed",
            description="d2",
            status="in_progress",
            priority=5,
            background_tasks=bt,
        )
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = bus.published
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["title", "description", "status", "priority"]
        assert updated.previous.title == "orig"
        assert updated.previous.description == "d1"
        assert updated.previous.status == "new"
        assert updated.previous.priority == 1
        assert updated.task.title == "renamed"
        assert updated.task.description == "d2"
        assert updated.task.status == "in_progress"
        assert updated.task.priority == 5
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status == "new"
        assert status_changed.to_status == "in_progress"

    async def test_replace_to_completing_state_fires_all_three_events_in_order(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=3, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description=None, status="completed", priority=3, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        completed = bus.published[2]
        assert isinstance(completed, TaskCompleted)
        assert completed.task.status == "completed"

    async def test_replace_non_status_field_only_fires_task_updated(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(title="a", description=None, status="new", priority=1, background_tasks=bt)
        bus.published.clear()
        await service.replace(1, title="a", description=None, status="new", priority=5, background_tasks=bt)
        assert [type(e) for e in bus.published] == [TaskUpdated]
        updated = bus.published[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["priority"]

    async def test_illegal_move_raises_invalid_transition(
        self, strict_service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await strict_service.create(title="a", description=None, status=None, priority=1, background_tasks=bt)
        bus.published.clear()
        with pytest.raises(InvalidTransitionError):
            await strict_service.replace(
                1, title="a", description=None, status="completed", priority=1, background_tasks=bt
            )
        assert bus.published == []

    async def test_unknown_id_raises_task_not_found(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.replace(999, title="x", description=None, status="new", priority=1, background_tasks=bt)
        assert bus.published == []


class TestDelete:
    async def test_fires_task_deleted_with_detached_snapshot(
        self, service: TaskService, repo: FakeRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        await service.create(
            title="alpha",
            description="d",
            status="in_progress",
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
        assert event.task.status == "in_progress"
        assert event.task.priority == 4
        # Snapshot must survive row deletion — the row is gone but the event still carries its data.
        assert 1 not in repo._rows  # pyright: ignore[reportPrivateUsage]

    async def test_unknown_id_raises_task_not_found(
        self, service: TaskService, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.delete(999, background_tasks=bt)
        assert bus.published == []
