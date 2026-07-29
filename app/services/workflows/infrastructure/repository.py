from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Column, func, select
from sqlmodel import Field, Session, SQLModel, col

from app.core.datetime_utils import ensure_utc
from app.core.errors import AppError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.interfaces import StoredWorkflow, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_from_document, workflow_to_document


class WorkflowRecord(SQLModel, table=True):
    """Persistence row — unlike ``Task``, the domain entity here is the parsed
    ``Workflow``; this record only stores its document form per version."""

    __tablename__ = "workflow_definitions"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    version: int = Field(index=True, unique=True)
    document: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), nullable=False)


class SQLModelWorkflowRepository(WorkflowRepositoryInterface):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_active(self) -> StoredWorkflow:
        record = self._session.scalars(
            select(WorkflowRecord).order_by(col(WorkflowRecord.version).desc()).limit(1)
        ).first()
        if record is None:
            # Broken startup invariant (seed did not run), not a client error.
            raise AppError(detail="No active workflow definition is stored.")
        return StoredWorkflow(
            workflow=workflow_from_document(record.document),
            version=record.version,
            created_at=ensure_utc(record.created_at),
        )

    def replace_active(self, workflow: Workflow) -> StoredWorkflow:
        highest = self._session.scalar(select(func.max(WorkflowRecord.version)))
        record = WorkflowRecord(version=(highest or 0) + 1, document=workflow_to_document(workflow))
        self._session.add(record)
        self._session.commit()
        return StoredWorkflow(
            workflow=workflow,
            version=record.version,
            created_at=ensure_utc(record.created_at),
        )
