from typing import Any, Self

from pydantic import BaseModel

from app.core.datetime_utils import IsoUtcDatetime
from app.services.workflows.interfaces import StoredWorkflow


class WorkflowResponse(BaseModel):
    version: int
    created_at: IsoUtcDatetime
    definition: dict[str, Any]

    @classmethod
    def from_stored(cls, stored: StoredWorkflow) -> Self:
        # ``definition`` is the canonical document the repository persisted, so
        # responses round-trip cleanly regardless of the caller's input spelling.
        return cls(
            version=stored.version,
            created_at=stored.created_at,
            definition=stored.document,
        )
