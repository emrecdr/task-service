from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.services.workflows.domain.definition import Workflow


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
    async def acquire_workflow_guard(self) -> None:
        """Serialise workflow-definition changes against status-changing task writes
        (transaction-scoped advisory lock; released at the span's commit)."""

    @abstractmethod
    async def get_active(self) -> StoredWorkflow: ...

    @abstractmethod
    async def replace_active(self, workflow: Workflow) -> StoredWorkflow: ...


class StatusUsagePort(ABC):
    """How many work items currently occupy each status — the only task-side
    fact the strand guard needs. A narrow, consumer-owned port (Interface
    Segregation): the workflows feature never receives full task-repo access."""

    @abstractmethod
    async def count_by_status(self) -> dict[str, int]: ...
