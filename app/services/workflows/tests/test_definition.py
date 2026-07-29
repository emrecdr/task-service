"""Workflow definition: transition rules, entry states, encapsulation."""

import pytest

from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State, Transition


def _board_workflow() -> Workflow:
    workflow = Workflow(states=[State("backlog", initial=True), State("todo"), State("in_progress"), State("done")])
    workflow.allow_transition("Plan", from_state="backlog", to_state="todo")
    workflow.allow_transition("Start work", from_state="todo", to_state="in_progress")
    workflow.allow_transition("Finish", from_state="in_progress", to_state="done")
    workflow.allow_transition("Send back", from_state="in_progress", to_state="todo")
    return workflow


def test_allow_rejects_unknown_states_and_duplicates() -> None:
    workflow = _board_workflow()

    with pytest.raises(ValueError, match="Unknown state"):
        workflow.allow_transition("Jump", from_state="todo", to_state="qa")
    with pytest.raises(ValueError, match="already defined"):
        workflow.allow_transition("Replan", from_state="backlog", to_state="todo")


def test_allow_accepts_custom_meta_fields() -> None:
    workflow = Workflow(states=[State("a"), State("b")])

    workflow.allow_transition("Go", from_state="a", to_state="b", color="#00f", limit=3)

    assert workflow.transitions[("a", "b")].meta == {"color": "#00f", "limit": 3}


def test_entry_states_default_to_first_state() -> None:
    workflow = Workflow(states=[State("a"), State("b")])

    assert workflow.entry_states == ["a"]
    assert workflow.default_entry == "a"


def test_entry_states_follow_initial_markers() -> None:
    workflow = Workflow(states=[State("a", initial=True), State("b", initial=True), State("c")])

    assert workflow.entry_states == ["a", "b"]


def test_transitions_from_and_moves_from_report_leaving_edges() -> None:
    workflow = _board_workflow()

    names = {t.name for t in workflow.transitions_from("in_progress")}

    assert names == {"Finish", "Send back"}
    assert workflow.moves_from("in_progress") == {"done", "todo"}


def test_state_accessor_returns_the_state_with_its_meta() -> None:
    workflow = Workflow(states=[State("a"), State("b", meta={"completes": True})])

    assert workflow.state("b").meta == {"completes": True}
    with pytest.raises(ValueError, match="Unknown state"):
        workflow.state("ghost")


def test_workflow_rejects_transition_filed_under_wrong_key() -> None:
    with pytest.raises(ValueError, match="wrong key"):
        Workflow(states=[State("a"), State("b")], transitions={("a", "a"): Transition("Go", "a", "b")})


def test_workflow_rejects_transitions_over_unknown_states() -> None:
    with pytest.raises(ValueError, match="Unknown state"):
        Workflow(states=[State("a"), State("b")], transitions={("a", "c"): Transition("Go", "a", "c")})


# ---------- Encapsulation: invariants cannot be bypassed from outside ----------


def test_states_and_transitions_are_read_only_views() -> None:
    workflow = Workflow(states=[State("a"), State("b")])
    workflow.allow_transition("Go", from_state="a", to_state="b")

    with pytest.raises(TypeError):
        workflow.transitions[("b", "a")] = Transition("Back", "b", "a")  # type: ignore[index]
    with pytest.raises(AttributeError):
        workflow.states.append(State("c"))  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        workflow.states = []  # type: ignore[misc]


def test_constructor_copies_its_inputs() -> None:
    states = [State("a")]
    workflow = Workflow(states=states)

    states.append(State("b"))  # mutating the caller's list must not reach inside

    assert workflow.state_names == ["a"]


def test_workflows_with_the_same_shape_are_equal() -> None:
    assert _board_workflow() == _board_workflow()
    assert _board_workflow() != Workflow(states=[State("a")])
