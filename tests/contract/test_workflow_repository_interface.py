from collections.abc import AsyncIterator, Callable

import pytest
from app.core import database
from app.core.errors import AppError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository, WorkflowRecord
from app.services.workflows.interfaces import WorkflowRepositoryInterface
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

type RepoBuilder = Callable[[], AsyncSession]


def _sqlmodel_session() -> AsyncSession:
    return database.get_sessionmaker()()


REPO_BUILDERS: list[RepoBuilder] = [_sqlmodel_session]


@pytest.fixture(params=REPO_BUILDERS, ids=lambda builder: builder.__name__.lstrip("_"))
async def repo(request: pytest.FixtureRequest) -> AsyncIterator[WorkflowRepositoryInterface]:
    session = request.param()
    try:
        yield SQLModelWorkflowRepository(session)
    finally:
        await session.close()


def _two_state_workflow() -> Workflow:
    workflow = Workflow(states=[State("a", initial=True), State("b")])
    workflow.allow_transition("Go", from_state="a", to_state="b")
    return workflow


async def test_replace_appends_versions_and_get_returns_highest(repo: WorkflowRepositoryInterface) -> None:
    first = await repo.replace_active(_two_state_workflow())

    second_workflow = Workflow(states=[State("a", initial=True), State("b"), State("c")])
    second_workflow.allow_transition("Go", from_state="a", to_state="b")
    second_workflow.allow_transition("On", from_state="b", to_state="c")
    second = await repo.replace_active(second_workflow)

    assert second.version == first.version + 1
    active = await repo.get_active()
    assert active.version == second.version
    assert active.workflow == second_workflow
    assert active.created_at is not None


async def test_round_trip_preserves_the_definition(repo: WorkflowRepositoryInterface) -> None:
    workflow = _two_state_workflow()

    await repo.replace_active(workflow)

    assert (await repo.get_active()).workflow == workflow


async def test_get_active_on_empty_table_raises_app_error(repo: WorkflowRepositoryInterface) -> None:
    # The conftest seed guarantees a row; remove every version to simulate the
    # broken-startup invariant this error exists for.
    async with AsyncSession(database.get_engine()) as session:
        for record in (await session.scalars(select(WorkflowRecord))).all():
            await session.delete(record)
        await session.commit()

    with pytest.raises(AppError):
        await repo.get_active()
