from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, field_serializer

from app.core.datetime_utils import iso_z
from app.services.workflows.interfaces import StoredWorkflow
from app.services.workflows.serialization import workflow_to_document


class WorkflowResponse(BaseModel):
    version: int
    created_at: datetime
    definition: dict[str, Any]

    @field_serializer("created_at")
    def _serialize_created_at(self, dt: datetime) -> str:
        return iso_z(dt)

    @classmethod
    def from_stored(cls, stored: StoredWorkflow) -> Self:
        # ``definition`` is always the canonical re-serialization, so responses
        # round-trip cleanly regardless of the caller's input spelling.
        return cls(
            version=stored.version,
            created_at=stored.created_at,
            definition=workflow_to_document(stored.workflow),
        )
