from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.services.workflows.domain.definition import Workflow


@dataclass(frozen=True, slots=True)
class StoredWorkflow:
    """A persisted definition: the parsed domain object plus its version row facts."""

    workflow: Workflow
    version: int
    created_at: datetime


class WorkflowRepositoryInterface(ABC):
    """Append-only storage: the active definition is the highest version."""

    @abstractmethod
    def get_active(self) -> StoredWorkflow: ...

    @abstractmethod
    def replace_active(self, workflow: Workflow) -> StoredWorkflow: ...
