"""Unit tests for WorkflowEngine — the state-machine rules any consumer drives."""

import pytest

from app.core.errors import InvalidTransitionError, UnknownStatusError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.engine import WorkflowEngine
from app.services.workflows.domain.models import State


def _strict() -> Workflow:
    """Single entry, one forward path: new -> in_progress -> completed(completes)."""
    workflow = Workflow(
        states=[
            State("new", initial=True),
            State("in_progress"),
            State("completed", meta={"completes": True}),
        ]
    )
    workflow.allow_transition("Start work", from_state="new", to_state="in_progress")
    workflow.allow_transition("Finish", from_state="in_progress", to_state="completed")
    return workflow


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine(_strict())


class TestResolveEntry:
    def test_none_resolves_to_default_entry(self, engine: WorkflowEngine) -> None:
        assert engine.resolve_entry(None) == "new"

    def test_known_entry_state_is_returned(self, engine: WorkflowEngine) -> None:
        assert engine.resolve_entry("new") == "new"

    def test_known_non_entry_state_raises_invalid_transition(self, engine: WorkflowEngine) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            engine.resolve_entry("completed")
        assert exc.value.details == {"from": None, "to": "completed", "allowed": ["new"]}

    def test_unknown_state_raises_unknown_status(self, engine: WorkflowEngine) -> None:
        with pytest.raises(UnknownStatusError) as exc:
            engine.resolve_entry("ghost")
        assert exc.value.details == {
            "field": "status",
            "value": "ghost",
            "known_states": ["new", "in_progress", "completed"],
        }


class TestCheckMove:
    def test_same_state_is_a_no_move(self, engine: WorkflowEngine) -> None:
        engine.check_move("new", "new")  # must not raise

    def test_legal_move_passes(self, engine: WorkflowEngine) -> None:
        engine.check_move("new", "in_progress")  # must not raise

    def test_illegal_move_raises_with_sorted_allowed(self, engine: WorkflowEngine) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            engine.check_move("new", "completed")
        assert exc.value.details == {"from": "new", "to": "completed", "allowed": ["in_progress"]}

    def test_unknown_target_raises_unknown_status(self, engine: WorkflowEngine) -> None:
        with pytest.raises(UnknownStatusError):
            engine.check_move("new", "ghost")


class TestCompletes:
    def test_true_when_state_carries_completes_meta(self, engine: WorkflowEngine) -> None:
        assert engine.completes("completed") is True

    def test_false_when_state_has_no_completes_meta(self, engine: WorkflowEngine) -> None:
        assert engine.completes("new") is False


class TestLegalMovesAndDefaultEntry:
    def test_default_entry_exposes_first_entry_state(self, engine: WorkflowEngine) -> None:
        assert engine.default_entry == "new"

    def test_legal_moves_lists_leaving_transitions(self, engine: WorkflowEngine) -> None:
        moves = engine.legal_moves("new")
        assert [(t.name, t.to_state) for t in moves] == [("Start work", "in_progress")]

    def test_legal_moves_empty_for_terminal_state(self, engine: WorkflowEngine) -> None:
        assert engine.legal_moves("completed") == []
