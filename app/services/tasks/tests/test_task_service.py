"""Service-layer unit tests for event-emission and workflow-enforcement rules.

Events are no longer published to a bus — the service hands them to the repository to stage in
the write's transaction. So the assertion seam is ``FakeRepo.events``: the events the service
passed to ``persist``/``remove`` for the last operation.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from app.core.constants import OrderDirection
from app.core.errors import (
    InvalidTransitionError,
    TransitionForbiddenError,
    UnknownStatusError,
    WipLimitExceededError,
)
from app.core.event_bus import Event
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
from app.services.tasks.errors import EmptyUpdateError, TaskNotFoundError
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State
from app.services.workflows.interfaces import StoredWorkflow, WorkflowEventFactory, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_to_document


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

    async def acquire_workflow_guard(self, *, shared: bool = False) -> None:
        return None

    async def get_active(self) -> StoredWorkflow:
        return StoredWorkflow(
            workflow=self._workflow,
            document=workflow_to_document(self._workflow),
            version=1,
            created_at=datetime.now(UTC),
        )

    async def replace_active(
        self, workflow: Workflow, *, make_events: WorkflowEventFactory | None = None
    ) -> StoredWorkflow:  # pragma: no cover - never called
        raise AssertionError("not used")


class FakeRepo(TaskRepositoryInterface):
    """In-memory repository that records the events it is asked to stage. ``persist`` mutates
    in place (the service mutates the fetched row, then persists the same object)."""

    def __init__(self) -> None:
        self._rows: dict[uuid.UUID, Task] = {}
        self.events: list[Event] = []
        self.count_calls = 0  # how many times occupancy was queried (WIP-limit gating)

    async def persist(self, task: Task, *, events: Sequence[Event]) -> None:
        self._rows[task.id] = task
        self.events.extend(events)

    async def get(self, task_id: uuid.UUID) -> Task:
        try:
            return self._rows[task_id]
        except KeyError as err:
            raise TaskNotFoundError(details={"id": str(task_id)}) from err

    async def list(
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

    async def remove(self, task: Task, *, events: Sequence[Event]) -> None:
        del self._rows[task.id]
        self.events.extend(events)

    async def count_by_status(self) -> dict[str, int]:
        self.count_calls += 1
        counts: dict[str, int] = {}
        for task in self._rows.values():
            counts[task.status] = counts.get(task.status, 0) + 1
        return counts


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def service(repo: FakeRepo) -> TaskService:
    return TaskService(repo=repo, workflows=FakeWorkflowRepo(_any_to_any()))


@pytest.fixture
def strict_service(repo: FakeRepo) -> TaskService:
    return TaskService(repo=repo, workflows=FakeWorkflowRepo(_strict()))


class TestCreate:
    async def test_stages_task_created_carrying_full_row(self, service: TaskService, repo: FakeRepo) -> None:
        task = await service.create(title="  Alpha  ", description="d", status="in_progress", priority=4)
        assert [type(e) for e in repo.events] == [TaskCreated]
        event = repo.events[0]
        assert isinstance(event, TaskCreated)
        assert event.task.id == task.id
        assert event.task.title == "Alpha"
        assert event.task.title_key == "alpha"
        assert event.task.description == "d"
        assert event.task.status == "in_progress"
        assert event.task.priority == 4

    async def test_omitted_status_resolves_to_default_entry(self, strict_service: TaskService) -> None:
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        assert task.status == "new"

    async def test_non_entry_status_raises_invalid_transition(
        self, strict_service: TaskService, repo: FakeRepo
    ) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.create(title="a", description=None, status="completed", priority=1)
        assert exc.value.details == {"from": None, "to": "completed", "allowed": ["new"]}
        assert repo.events == []

    async def test_unknown_status_raises_unknown_status(self, strict_service: TaskService, repo: FakeRepo) -> None:
        with pytest.raises(UnknownStatusError) as exc:
            await strict_service.create(title="a", description=None, status="ghost", priority=1)
        assert exc.value.details == {
            "field": "status",
            "value": "ghost",
            "known_states": ["new", "in_progress", "completed"],
        }
        assert repo.events == []


class TestLegalMoves:
    async def test_returns_task_and_leaving_transitions(self, strict_service: TaskService) -> None:
        created = await strict_service.create(title="a", description=None, status=None, priority=1)

        task, transitions = await strict_service.legal_moves(created.id)

        assert task.status == "new"
        assert [(t.name, t.to_state) for t in transitions] == [("Start work", "in_progress")]

    async def test_unknown_id_raises_task_not_found(self, strict_service: TaskService) -> None:
        with pytest.raises(TaskNotFoundError):
            await strict_service.legal_moves(uuid.uuid4())


class TestPatch:
    async def test_empty_body_raises_empty_update(self, service: TaskService) -> None:
        with pytest.raises(EmptyUpdateError):
            await service.patch(uuid.uuid4(), fields={})

    async def test_no_actual_change_does_not_stage_updated(self, service: TaskService, repo: FakeRepo) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.patch(task.id, fields={"priority": 1})
        assert repo.events == []

    async def test_same_state_patch_needs_no_transition_and_stages_no_events(
        self, strict_service: TaskService, repo: FakeRepo
    ) -> None:
        # The strict workflow has no new -> new transition; a same-state write
        # must still succeed as a no-move.
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        repo.events.clear()
        await strict_service.patch(task.id, fields={"status": "new"})
        assert repo.events == []

    async def test_illegal_move_raises_invalid_transition_with_allowed_list(
        self, strict_service: TaskService, repo: FakeRepo
    ) -> None:
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        repo.events.clear()
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.patch(task.id, fields={"status": "completed"})
        assert exc.value.details == {"from": "new", "to": "completed", "allowed": ["in_progress"]}
        assert repo.events == []

    async def test_unknown_target_state_raises_unknown_status(
        self, strict_service: TaskService, repo: FakeRepo
    ) -> None:
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        repo.events.clear()
        with pytest.raises(UnknownStatusError):
            await strict_service.patch(task.id, fields={"status": "ghost"})
        assert repo.events == []

    async def test_status_to_in_progress_stages_updated_then_status_changed(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.patch(task.id, fields={"status": "in_progress"})
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = repo.events
        assert isinstance(updated, TaskUpdated)
        assert updated.previous.status == "new"
        assert updated.task.status == "in_progress"
        assert updated.changed_fields == ["status"]
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status == "new"
        assert status_changed.to_status == "in_progress"
        assert status_changed.task.id == task.id

    async def test_entering_completing_state_stages_three_events_in_order(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.patch(task.id, fields={"status": "completed"})
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        updated, status_changed, completed = repo.events
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["status"]
        assert updated.previous.status == "new"
        assert updated.task.status == "completed"
        assert isinstance(status_changed, TaskStatusChanged)
        assert status_changed.from_status == "new"
        assert status_changed.to_status == "completed"
        assert isinstance(completed, TaskCompleted)
        assert completed.task.id == task.id
        assert completed.task.status == "completed"

    async def test_entering_non_completing_state_does_not_stage_completed(self, repo: FakeRepo) -> None:
        # "done" carries no completes meta — TaskCompleted must stay silent.
        workflow = Workflow(states=[State("open", initial=True), State("done")])
        workflow.allow_transition("Close", from_state="open", to_state="done")
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(workflow))
        task = await service.create(title="a", description=None, status=None, priority=1)
        repo.events.clear()

        await service.patch(task.id, fields={"status": "done"})

        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged]

    async def test_non_status_change_stages_only_task_updated_with_field_list(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.patch(task.id, fields={"priority": 5})
        assert [type(e) for e in repo.events] == [TaskUpdated]
        updated = repo.events[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["priority"]
        assert updated.previous.priority == 1
        assert updated.task.priority == 5

    async def test_multi_field_change_lists_fields_in_canonical_order(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        # MUTABLE_FIELDS order = ("title", "description", "status", "priority").
        # changed_fields must follow this order even if input dict shuffles them.
        await service.patch(task.id, fields={"priority": 5, "title": "renamed", "description": "d"})
        updated = repo.events[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["title", "description", "priority"]

    async def test_unknown_id_raises_task_not_found(self, service: TaskService, repo: FakeRepo) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.patch(uuid.uuid4(), fields={"priority": 5})
        assert repo.events == []


class TestReplace:
    async def test_no_actual_change_does_not_stage_updated(self, service: TaskService, repo: FakeRepo) -> None:
        task = await service.create(title="a", description="d", status="new", priority=3)
        repo.events.clear()
        await service.replace(task.id, title="a", description="d", status="new", priority=3)
        assert repo.events == []

    async def test_omitted_status_resolves_to_default_entry_and_move_checks(
        self, strict_service: TaskService, repo: FakeRepo
    ) -> None:
        # in_progress -> new is not a strict-workflow transition, so a PUT that
        # omits status while the task is mid-flow is a loud 409, not a silent reset.
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        await strict_service.patch(task.id, fields={"status": "in_progress"})
        repo.events.clear()
        with pytest.raises(InvalidTransitionError) as exc:
            await strict_service.replace(task.id, title="a", description=None, status=None, priority=1)
        assert exc.value.details == {"from": "in_progress", "to": "new", "allowed": ["completed"]}
        assert repo.events == []

    async def test_full_replace_stages_updated_with_all_changed_fields(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="orig", description="d1", status="new", priority=1)
        repo.events.clear()
        await service.replace(task.id, title="renamed", description="d2", status="in_progress", priority=5)
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged]
        updated, status_changed = repo.events
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

    async def test_replace_to_completing_state_stages_all_three_events_in_order(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=3)
        repo.events.clear()
        await service.replace(task.id, title="a", description=None, status="completed", priority=3)
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged, TaskCompleted]
        completed = repo.events[2]
        assert isinstance(completed, TaskCompleted)
        assert completed.task.status == "completed"

    async def test_replace_non_status_field_only_stages_task_updated(
        self, service: TaskService, repo: FakeRepo
    ) -> None:
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.replace(task.id, title="a", description=None, status="new", priority=5)
        assert [type(e) for e in repo.events] == [TaskUpdated]
        updated = repo.events[0]
        assert isinstance(updated, TaskUpdated)
        assert updated.changed_fields == ["priority"]

    async def test_illegal_move_raises_invalid_transition(self, strict_service: TaskService, repo: FakeRepo) -> None:
        task = await strict_service.create(title="a", description=None, status=None, priority=1)
        repo.events.clear()
        with pytest.raises(InvalidTransitionError):
            await strict_service.replace(task.id, title="a", description=None, status="completed", priority=1)
        assert repo.events == []

    async def test_unknown_id_raises_task_not_found(self, service: TaskService, repo: FakeRepo) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.replace(uuid.uuid4(), title="x", description=None, status="new", priority=1)
        assert repo.events == []


class TestDelete:
    async def test_stages_task_deleted_with_detached_snapshot(self, service: TaskService, repo: FakeRepo) -> None:
        task = await service.create(title="alpha", description="d", status="in_progress", priority=4)
        repo.events.clear()
        await service.delete(task.id)
        assert [type(e) for e in repo.events] == [TaskDeleted]
        event = repo.events[0]
        assert isinstance(event, TaskDeleted)
        assert event.task.id == task.id
        assert event.task.title == "alpha"
        assert event.task.description == "d"
        assert event.task.status == "in_progress"
        assert event.task.priority == 4
        # Snapshot must survive row deletion — the row is gone but the event still carries its data.
        assert task.id not in repo._rows  # pyright: ignore[reportPrivateUsage]

    async def test_unknown_id_raises_task_not_found(self, service: TaskService, repo: FakeRepo) -> None:
        with pytest.raises(TaskNotFoundError):
            await service.delete(uuid.uuid4())
        assert repo.events == []


def _role_guarded() -> Workflow:
    workflow = Workflow(states=[State("new", initial=True), State("done", meta={"completes": True})])
    workflow.allow_transition("Approve", from_state="new", to_state="done", roles=["manager"])
    return workflow


def _wip_limited() -> Workflow:
    workflow = Workflow(states=[State("new", initial=True), State("active", meta={"wip_limit": 1})])
    workflow.allow_transition("Activate", from_state="new", to_state="active")
    return workflow


def _wip_limited_entry() -> Workflow:
    """The capped state is itself an entry state, so a *create* can hit the limit — the branch
    guarded by ``resolve_entry`` rather than ``check_move``."""
    workflow = Workflow(states=[State("new", initial=True), State("active", initial=True, meta={"wip_limit": 1})])
    workflow.allow_transition("Activate", from_state="new", to_state="active")
    return workflow


class TestRoleGuards:
    async def test_transition_forbidden_without_the_required_role(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_role_guarded()))
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        with pytest.raises(TransitionForbiddenError) as exc:
            await service.patch(task.id, fields={"status": "done"})  # no X-Roles
        assert exc.value.details["required_roles"] == ["manager"]
        assert repo.events == []  # a forbidden move stages nothing

    async def test_transition_allowed_with_the_required_role(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_role_guarded()))
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        await service.patch(task.id, fields={"status": "done"}, roles=frozenset({"manager"}))
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged, TaskCompleted]

    async def test_replace_is_guarded_by_the_same_roles(self, repo: FakeRepo) -> None:
        # ``replace`` carries its own ``roles`` seam; a guard enforced only on ``patch`` would
        # leave the whole PUT path unauthorized.
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_role_guarded()))
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        with pytest.raises(TransitionForbiddenError) as exc:
            await service.replace(task.id, title="a", description=None, status="done", priority=1)
        assert exc.value.details["required_roles"] == ["manager"]
        assert repo.events == []

    async def test_replace_allowed_with_the_required_role(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_role_guarded()))
        task = await service.create(title="a", description=None, status="new", priority=1)
        repo.events.clear()
        replaced = await service.replace(
            task.id, title="a", description=None, status="done", priority=1, roles=frozenset({"manager"})
        )
        assert replaced.status == "done"
        assert [type(e) for e in repo.events] == [TaskUpdated, TaskStatusChanged, TaskCompleted]


class TestWipLimits:
    async def test_entry_blocked_when_target_state_is_full(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        first = await service.create(title="a", description=None, status="new", priority=1)
        await service.patch(first.id, fields={"status": "active"})  # fills "active" (limit 1)
        second = await service.create(title="b", description=None, status="new", priority=1)
        repo.events.clear()
        with pytest.raises(WipLimitExceededError) as exc:
            await service.patch(second.id, fields={"status": "active"})
        assert exc.value.details == {"state": "active", "limit": 1, "current": 1}
        assert repo.events == []

    async def test_entry_allowed_below_the_limit(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        task = await service.create(title="a", description=None, status="new", priority=1)
        moved = await service.patch(task.id, fields={"status": "active"})
        assert moved.status == "active"

    async def test_create_into_a_full_entry_state_is_refused(self, repo: FakeRepo) -> None:
        # The create branch runs through ``resolve_entry``, a different engine method than the
        # move branch — a limit dropped from one would still pass the other's tests.
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited_entry()))
        await service.create(title="a", description=None, status="active", priority=1)  # fills it
        repo.events.clear()
        with pytest.raises(WipLimitExceededError) as exc:
            await service.create(title="b", description=None, status="active", priority=1)
        assert exc.value.details == {"state": "active", "limit": 1, "current": 1}
        assert repo.events == []

    async def test_replace_is_wip_limited(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        first = await service.create(title="a", description=None, status="new", priority=1)
        await service.patch(first.id, fields={"status": "active"})  # fills "active" (limit 1)
        second = await service.create(title="b", description=None, status="new", priority=1)
        repo.events.clear()
        with pytest.raises(WipLimitExceededError):
            await service.replace(second.id, title="b", description=None, status="active", priority=1)
        assert repo.events == []


class TestOccupancyGating:
    """The occupancy count is issued only for writes that can actually hit a ``wip_limit`` —
    the engine decides (``needs_occupancy``), so these pin the query, not the rule."""

    async def test_never_queried_without_a_wip_limit_anywhere(self, repo: FakeRepo) -> None:
        guardless = TaskService(repo=repo, workflows=FakeWorkflowRepo(_any_to_any()))
        task = await guardless.create(title="a", description=None, status="new", priority=1)
        await guardless.patch(task.id, fields={"status": "in_progress"})
        assert repo.count_calls == 0

    async def test_not_queried_when_the_entered_state_is_uncapped(self, repo: FakeRepo) -> None:
        # A cap on some *other* state must not make every unrelated write pay for a count.
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        await service.create(title="a", description=None, status="new", priority=1)
        assert repo.count_calls == 0

    async def test_not_queried_when_the_write_enters_no_state(self, repo: FakeRepo) -> None:
        # Same-state writes are no-moves: nothing is entered, so no limit can fire.
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        task = await service.create(title="a", description=None, status="new", priority=1)

        await service.patch(task.id, fields={"status": "new", "priority": 5})
        await service.replace(task.id, title="a", description=None, status="new", priority=4)
        assert repo.count_calls == 0

    async def test_queried_when_entering_a_capped_state(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited()))
        task = await service.create(title="a", description=None, status="new", priority=1)

        await service.patch(task.id, fields={"status": "active"})
        assert repo.count_calls == 1

    async def test_queried_when_a_create_names_a_capped_entry_state(self, repo: FakeRepo) -> None:
        service = TaskService(repo=repo, workflows=FakeWorkflowRepo(_wip_limited_entry()))
        await service.create(title="a", description=None, status="active", priority=1)
        assert repo.count_calls == 1
