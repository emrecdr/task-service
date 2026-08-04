"""Service-layer unit tests: strand guard, validation, event emission.

Events are staged in the write's transaction, not published to a bus — so the assertion seam is
``FakeWorkflowRepo.emitted``: whatever the service's ``make_events`` closure produced for the
version the repo assigned.
"""

from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.event_bus import Event
from app.services.workflows.application.service import WorkflowService
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.events import WorkflowUpdated
from app.services.workflows.errors import WorkflowStatesInUseError, WorkflowValidationError
from app.services.workflows.interfaces import (
    StatusUsagePort,
    StoredWorkflow,
    WorkflowEventFactory,
    WorkflowRepositoryInterface,
)
from app.services.workflows.serialization import workflow_to_document

_VALID_DOCUMENT: dict[str, Any] = {
    "states": [{"name": "open", "initial": True}, "closed"],
    "transitions": [{"name": "Close", "from": "open", "to": "closed"}],
}


class FakeWorkflowRepo(WorkflowRepositoryInterface):
    def __init__(self) -> None:
        self.stored: list[StoredWorkflow] = []
        self.emitted: list[Event] = []

    async def acquire_workflow_guard(self, *, shared: bool = False) -> None:
        return None

    async def get_active(self) -> StoredWorkflow:
        return self.stored[-1]

    async def replace_active(
        self, workflow: Workflow, *, make_events: WorkflowEventFactory | None = None
    ) -> StoredWorkflow:
        version = len(self.stored) + 1
        record = StoredWorkflow(
            workflow=workflow,
            document=workflow_to_document(workflow),
            version=version,
            created_at=datetime.now(UTC),
        )
        self.stored.append(record)
        if make_events is not None:
            self.emitted.extend(make_events(version))
        return record


class StubStatusUsage(StatusUsagePort):
    """The only task-side fact the strand guard consults — status occupancy counts."""

    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    async def count_by_status(self) -> dict[str, int]:
        return self._counts


@pytest.fixture
def repo() -> FakeWorkflowRepo:
    return FakeWorkflowRepo()


def _service(repo: FakeWorkflowRepo, counts: dict[str, int] | None = None) -> WorkflowService:
    return WorkflowService(repo=repo, usage=StubStatusUsage(counts or {}))


class TestReplaceActive:
    async def test_valid_document_is_stored_and_returned(self, repo: FakeWorkflowRepo) -> None:
        service = _service(repo)

        stored = await service.replace_active(document=_VALID_DOCUMENT)

        assert stored.version == 1
        assert workflow_to_document(stored.workflow) == workflow_to_document(repo.stored[0].workflow)
        assert stored.workflow.state_names == ["open", "closed"]

    async def test_stages_workflow_updated_with_version_and_states(self, repo: FakeWorkflowRepo) -> None:
        service = _service(repo)

        await service.replace_active(document=_VALID_DOCUMENT)

        assert [type(e) for e in repo.emitted] == [WorkflowUpdated]
        event = repo.emitted[0]
        assert isinstance(event, WorkflowUpdated)
        assert event.version == 1
        assert event.states == ["open", "closed"]

    async def test_invalid_document_collects_all_errors_and_stores_nothing(self, repo: FakeWorkflowRepo) -> None:
        service = _service(repo)
        document = {"states": ["a", "a"], "transitions": [{"name": "", "from": "a", "to": "ghost"}]}

        with pytest.raises(WorkflowValidationError) as exc_info:
            await service.replace_active(document=document)

        assert len(exc_info.value.errors) == 3
        assert repo.stored == []
        assert repo.emitted == []

    async def test_stranding_definition_raises_with_live_counts(self, repo: FakeWorkflowRepo) -> None:
        service = _service(repo, counts={"open": 1, "done": 2})

        with pytest.raises(WorkflowStatesInUseError) as exc_info:
            await service.replace_active(document=_VALID_DOCUMENT)

        assert exc_info.value.details == {"states": {"done": 2}}
        assert repo.stored == []
        assert repo.emitted == []


class TestGetActive:
    async def test_returns_the_repositories_active_definition(self, repo: FakeWorkflowRepo) -> None:
        service = _service(repo)
        stored = await service.replace_active(document=_VALID_DOCUMENT)

        assert await service.get_active() == stored
