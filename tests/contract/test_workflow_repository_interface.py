from collections.abc import Callable, Iterator

import pytest
from app.core.database import engine
from app.core.errors import AppError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository, WorkflowRecord
from app.services.workflows.interfaces import WorkflowRepositoryInterface
from sqlmodel import Session, select

type RepoFactory = Callable[[], tuple[WorkflowRepositoryInterface, Callable[[], None]]]


def _sqlmodel_repo() -> tuple[WorkflowRepositoryInterface, Callable[[], None]]:
    session = Session(engine)
    return SQLModelWorkflowRepository(session), session.close


REPO_BUILDERS: list[RepoFactory] = [_sqlmodel_repo]


@pytest.fixture(params=REPO_BUILDERS, ids=lambda factory: factory.__name__.lstrip("_"))
def repo(request: pytest.FixtureRequest) -> Iterator[WorkflowRepositoryInterface]:
    instance, teardown = request.param()
    try:
        yield instance
    finally:
        teardown()


def _two_state_workflow() -> Workflow:
    workflow = Workflow(states=[State("a", initial=True), State("b")])
    workflow.allow_transition("Go", from_state="a", to_state="b")
    return workflow


def test_replace_appends_versions_and_get_returns_highest(repo: WorkflowRepositoryInterface) -> None:
    first = repo.replace_active(_two_state_workflow())

    second_workflow = Workflow(states=[State("a", initial=True), State("b"), State("c")])
    second_workflow.allow_transition("Go", from_state="a", to_state="b")
    second_workflow.allow_transition("On", from_state="b", to_state="c")
    second = repo.replace_active(second_workflow)

    assert second.version == first.version + 1
    active = repo.get_active()
    assert active.version == second.version
    assert active.workflow == second_workflow
    assert active.created_at is not None


def test_round_trip_preserves_the_definition(repo: WorkflowRepositoryInterface) -> None:
    workflow = _two_state_workflow()

    repo.replace_active(workflow)

    assert repo.get_active().workflow == workflow


def test_get_active_on_empty_table_raises_app_error(repo: WorkflowRepositoryInterface) -> None:
    # The conftest seed guarantees a row; remove every version to simulate the
    # broken-startup invariant this error exists for.
    with Session(engine) as session:
        for record in session.exec(select(WorkflowRecord)).all():
            session.delete(record)
        session.commit()

    with pytest.raises(AppError):
        repo.get_active()
