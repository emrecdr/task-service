"""First-boot seed: store the default definition when the table is empty."""

from sqlalchemy import select
from sqlmodel import col

from app.core.database import session_factory
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import COMPLETES_META_KEY, State
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository, WorkflowRecord


def default_workflow() -> Workflow:
    """The behavior-identical default: three states, any → any.

    Every state is ``initial`` because creates historically accepted any
    status; ``default_entry`` stays "new" (first initial). A richer policy
    is one ``PUT /v1/workflow`` away — this seed is mechanism, not policy.
    """
    workflow = Workflow(
        states=[
            State("new", initial=True),
            State("in_progress", initial=True),
            # Interpreted by the tasks feature (fires TaskCompleted).
            State("completed", initial=True, meta={COMPLETES_META_KEY: True}),
        ]
    )
    workflow.allow_transition("Start work", from_state="new", to_state="in_progress")
    workflow.allow_transition("Complete", from_state="new", to_state="completed")
    workflow.allow_transition("Complete", from_state="in_progress", to_state="completed")
    workflow.allow_transition("Send back", from_state="in_progress", to_state="new")
    workflow.allow_transition("Reopen", from_state="completed", to_state="new")
    workflow.allow_transition("Resume", from_state="completed", to_state="in_progress")
    return workflow


async def seed_workflow_if_missing() -> None:
    """Idempotent and multi-worker-safe: the advisory guard serialises concurrent
    workers so exactly one inserts version 1 (the rest see it present and skip).
    Called from both the app lifespan and the test schema reset."""
    async with session_factory() as session:
        repo = SQLModelWorkflowRepository(session)
        await repo.acquire_workflow_guard()
        if await session.scalar(select(col(WorkflowRecord.id)).limit(1)) is None:
            await repo.replace_active(default_workflow())
