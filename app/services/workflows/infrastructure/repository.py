from datetime import UTC, datetime
from typing import Any, Final

from sqlalchemy import Column, DateTime, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, col

from app.core.datetime_utils import ensure_utc
from app.core.errors import AppError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.interfaces import StoredWorkflow, WorkflowRepositoryInterface
from app.services.workflows.serialization import workflow_from_document, workflow_to_document

# Postgres advisory-lock key serialising the "workflow-definition vs task-status"
# critical section (see WorkflowEngine / the strand guard). Transaction-scoped, so it
# releases at the span's single commit — this is what restores the atomicity the
# single shared connection would otherwise provide for free.
_WORKFLOW_GUARD_KEY: Final[int] = 0x776B666C  # 'wkfl'
# Reader/writer forms of the guard: task-status writes take SHARED (run concurrently — they
# only read the definition); workflow replacement + seed take EXCLUSIVE (waits for / blocks
# shared holders). Static clauses so no SQL is ever string-built.
_EXCLUSIVE_GUARD_SQL: Final = text("SELECT pg_advisory_xact_lock(:k)")
_SHARED_GUARD_SQL: Final = text("SELECT pg_advisory_xact_lock_shared(:k)")


class WorkflowRecord(SQLModel, table=True):
    """Persistence row — unlike ``Task``, the domain entity here is the parsed
    ``Workflow``; this record only stores its document form per version."""

    __tablename__ = "workflow_definitions"  # pyright: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    version: int = Field(index=True, unique=True)
    document: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),  # timestamptz
    )


class SQLModelWorkflowRepository(WorkflowRepositoryInterface):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_workflow_guard(self, *, shared: bool = False) -> None:
        """Take the transaction-scoped advisory guard — SHARED for task-status writes (they
        run concurrently) or EXCLUSIVE for workflow replacement + seed. Released automatically
        when this session's transaction commits or rolls back."""
        await self._session.execute(_SHARED_GUARD_SQL if shared else _EXCLUSIVE_GUARD_SQL, {"k": _WORKFLOW_GUARD_KEY})

    async def get_active(self) -> StoredWorkflow:
        result = await self._session.scalars(
            select(WorkflowRecord).order_by(col(WorkflowRecord.version).desc()).limit(1)
        )
        record = result.first()
        if record is None:
            # Broken startup invariant (seed did not run), not a client error.
            raise AppError(detail="No active workflow definition is stored.")
        return StoredWorkflow(
            workflow=workflow_from_document(record.document),
            document=record.document,
            version=record.version,
            created_at=ensure_utc(record.created_at),
        )

    async def replace_active(self, workflow: Workflow) -> StoredWorkflow:
        highest = await self._session.scalar(select(func.max(WorkflowRecord.version)))
        document = workflow_to_document(workflow)
        record = WorkflowRecord(version=(highest or 0) + 1, document=document)
        self._session.add(record)
        await self._session.commit()
        return StoredWorkflow(
            workflow=workflow,
            document=document,
            version=record.version,
            created_at=ensure_utc(record.created_at),
        )
