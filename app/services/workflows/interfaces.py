from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core.event_bus import Event
from app.services.workflows.domain.definition import Workflow

# Given the version the repo is about to assign, produce the events to stage with it. The
# repo owns version assignment, so the service passes this closure rather than pre-built
# events — keeping the "which event fires" decision in the service (asserted at the unit
# layer) while the repo keeps the write and its outbox rows atomic. ``None`` ⇒ emit nothing
# (the seed path, which is not a client-driven change and fires no ``WorkflowUpdated``).
type WorkflowEventFactory = Callable[[int], Sequence[Event]]


@dataclass(frozen=True, slots=True)
class StoredWorkflow:
    """A persisted definition: the parsed domain object, its canonical document, and version row facts.

    ``document`` is the canonical serialization the repository already holds — carried
    here so read/write responses need not re-serialize ``workflow`` a second time.
    """

    workflow: Workflow
    document: dict[str, Any]
    version: int
    created_at: datetime


class WorkflowRepositoryInterface(ABC):
    """Append-only storage: the active definition is the highest version."""

    @abstractmethod
    async def acquire_workflow_guard(self, *, shared: bool = False) -> None:
        """Serialise the workflow-definition-vs-task-status critical section with a
        transaction-scoped advisory lock (released at the span's commit).

        ``shared=True`` (task-status writes) takes a SHARED lock — many run concurrently
        since they only *read* the active definition. ``shared=False`` (``PUT /v1/workflow``
        and the seed) takes the EXCLUSIVE lock, which waits for all shared holders and blocks
        new ones, so a redefinition still mutually excludes every in-flight task write (the
        anti-stranding invariant) without task writes serialising against each other."""

    @abstractmethod
    async def get_active(self) -> StoredWorkflow: ...

    @abstractmethod
    async def replace_active(
        self,
        workflow: Workflow,
        *,
        make_events: WorkflowEventFactory | None = None,
    ) -> StoredWorkflow:
        """Store ``workflow`` as the next version and stage the events ``make_events`` returns
        for that version, atomically in one commit (the seed passes ``None``: no events)."""


class StatusUsagePort(ABC):
    """How many work items currently occupy each status — the only task-side
    fact the strand guard needs. A narrow, consumer-owned port (Interface
    Segregation): the workflows feature never receives full task-repo access."""

    @abstractmethod
    async def count_by_status(self) -> dict[str, int]: ...
