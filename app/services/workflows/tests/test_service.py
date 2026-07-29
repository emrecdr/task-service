"""Service-layer unit tests: strand guard, validation, event publishing."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import BackgroundTasks

from app.core.event_bus import Event, EventBus
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.application.service import WorkflowService
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.events import WorkflowUpdated
from app.services.workflows.errors import WorkflowStatesInUseError, WorkflowValidationError
from app.services.workflows.interfaces import StoredWorkflow, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_to_document

_VALID_DOCUMENT: dict[str, Any] = {
    "states": [{"name": "open", "initial": True}, "closed"],
    "transitions": [{"name": "Close", "from": "open", "to": "closed"}],
}


class FakeWorkflowRepo(WorkflowRepositoryInterface):
    def __init__(self) -> None:
        self.stored: list[StoredWorkflow] = []

    def get_active(self) -> StoredWorkflow:
        return self.stored[-1]

    def replace_active(self, workflow: Workflow) -> StoredWorkflow:
        record = StoredWorkflow(workflow=workflow, version=len(self.stored) + 1, created_at=datetime.now(UTC))
        self.stored.append(record)
        return record


class StubTaskRepo(TaskRepositoryInterface):
    """Only ``count_by_status`` is consulted by the workflow service."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    def count_by_status(self) -> dict[str, int]:
        return self._counts

    def add(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")

    def get(self, task_id: int) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")

    def list(self, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")

    def replace(self, task_id: int, **kwargs: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")

    def patch(self, task_id: int, **fields: Any) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")

    def delete(self, task_id: int) -> Any:  # pragma: no cover - never called
        raise AssertionError("not used")


class RecordingBus(EventBus):
    def __init__(self) -> None:
        super().__init__()
        self.published: list[Event] = []

    def publish(self, event: Event, background_tasks: BackgroundTasks) -> None:
        self.published.append(event)


@pytest.fixture
def repo() -> FakeWorkflowRepo:
    return FakeWorkflowRepo()


@pytest.fixture
def bus() -> RecordingBus:
    return RecordingBus()


@pytest.fixture
def bt() -> BackgroundTasks:
    return BackgroundTasks()


def _service(repo: FakeWorkflowRepo, bus: RecordingBus, counts: dict[str, int] | None = None) -> WorkflowService:
    return WorkflowService(repo=repo, tasks=StubTaskRepo(counts or {}), events=bus)


class TestReplaceActive:
    async def test_valid_document_is_stored_and_returned(
        self, repo: FakeWorkflowRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        service = _service(repo, bus)

        stored = await service.replace_active(document=_VALID_DOCUMENT, background_tasks=bt)

        assert stored.version == 1
        assert workflow_to_document(stored.workflow) == workflow_to_document(repo.stored[0].workflow)
        assert stored.workflow.state_names == ["open", "closed"]

    async def test_fires_workflow_updated_with_version_and_states(
        self, repo: FakeWorkflowRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        service = _service(repo, bus)

        await service.replace_active(document=_VALID_DOCUMENT, background_tasks=bt)

        assert [type(e) for e in bus.published] == [WorkflowUpdated]
        event = bus.published[0]
        assert isinstance(event, WorkflowUpdated)
        assert event.version == 1
        assert event.states == ["open", "closed"]

    async def test_invalid_document_collects_all_errors_and_stores_nothing(
        self, repo: FakeWorkflowRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        service = _service(repo, bus)
        document = {"states": ["a", "a"], "transitions": [{"name": "", "from": "a", "to": "ghost"}]}

        with pytest.raises(WorkflowValidationError) as exc_info:
            await service.replace_active(document=document, background_tasks=bt)

        assert len(exc_info.value.errors) == 3
        assert repo.stored == []
        assert bus.published == []

    async def test_stranding_definition_raises_with_live_counts(
        self, repo: FakeWorkflowRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        service = _service(repo, bus, counts={"open": 1, "done": 2})

        with pytest.raises(WorkflowStatesInUseError) as exc_info:
            await service.replace_active(document=_VALID_DOCUMENT, background_tasks=bt)

        assert exc_info.value.details == {"states": {"done": 2}}
        assert repo.stored == []
        assert bus.published == []


class TestGetActive:
    async def test_returns_the_repositories_active_definition(
        self, repo: FakeWorkflowRepo, bus: RecordingBus, bt: BackgroundTasks
    ) -> None:
        service = _service(repo, bus)
        stored = await service.replace_active(document=_VALID_DOCUMENT, background_tasks=bt)

        assert await service.get_active() == stored
