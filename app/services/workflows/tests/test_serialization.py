"""Document boundary: round-trips and collect-all-errors validation."""

import pytest

from app.core.errors import ErrorCode, ValidationError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import State
from app.services.workflows.errors import WorkflowValidationError
from app.services.workflows.serialization import workflow_from_document, workflow_to_document


def _rich_workflow() -> Workflow:
    workflow = Workflow(
        states=[State("backlog", initial=True), State("todo"), State("in_progress"), State("review"), State("done")]
    )
    workflow.allow_transition("Plan", from_state="backlog", to_state="todo")
    workflow.allow_transition("Start work", from_state="todo", to_state="in_progress")
    workflow.allow_transition("Request review", from_state="in_progress", to_state="review", color="#00f", limit=3)
    workflow.allow_transition("Approve", from_state="review", to_state="done")
    return workflow


def test_document_round_trip_preserves_workflow_names_and_meta() -> None:
    workflow = _rich_workflow()

    restored = workflow_from_document(workflow_to_document(workflow))

    assert restored == workflow
    assert restored.states == workflow.states  # column order survives
    assert restored.transitions[("in_progress", "review")].name == "Request review"
    assert restored.transitions[("in_progress", "review")].meta == {"color": "#00f", "limit": 3}


def test_from_document_collects_unknown_keys_as_meta() -> None:
    document = {"states": ["a", "b"], "transitions": [{"name": "Go", "from": "a", "to": "b", "color": "#00f"}]}

    workflow = workflow_from_document(document)

    assert workflow.transitions[("a", "b")].meta == {"color": "#00f"}


def test_from_document_parses_state_objects_and_shorthand() -> None:
    document = {
        "states": [{"name": "a", "initial": True, "wip_limit": 2}, "b"],
        "transitions": [{"name": "Go", "from": "a", "to": "b"}],
    }

    workflow = workflow_from_document(document)

    assert workflow.entry_states == ["a"]
    assert workflow.states[0].meta == {"wip_limit": 2}
    assert workflow.states[1] == State("b")


def test_state_properties_survive_round_trip() -> None:
    document = {
        "states": [{"name": "a", "initial": True}, {"name": "b", "color": "#333"}],
        "transitions": [{"name": "Go", "from": "a", "to": "b"}],
    }
    workflow = workflow_from_document(document)

    restored = workflow_from_document(workflow_to_document(workflow))

    assert restored == workflow
    assert restored.entry_states == ["a"]
    assert restored.states[1].meta == {"color": "#333"}


def test_from_document_rejects_bad_state_objects() -> None:
    with pytest.raises(WorkflowValidationError, match="'initial' must be a boolean"):
        workflow_from_document({"states": [{"name": "a", "initial": "yes"}], "transitions": []})
    with pytest.raises(WorkflowValidationError, match="requires a non-empty string 'name'"):
        workflow_from_document({"states": [{"initial": True}], "transitions": []})


def test_from_document_rejects_malformed_shapes() -> None:
    with pytest.raises(WorkflowValidationError, match="must be a JSON object"):
        workflow_from_document(["a", "b"])
    with pytest.raises(WorkflowValidationError, match="'transitions' must be a list"):
        workflow_from_document({"states": ["a"]})
    with pytest.raises(WorkflowValidationError, match="missing field"):
        workflow_from_document({"states": ["a", "b"], "transitions": [{"from": "a", "to": "b"}]})


def test_from_document_rejects_empty_states() -> None:
    # Mirrors minItems: 1 — the constructor's raw ValueError must never leak.
    with pytest.raises(WorkflowValidationError, match="at least one state"):
        workflow_from_document({"states": [], "transitions": []})


def test_from_document_rejects_unknown_top_level_keys() -> None:
    # Top-level extras have no meta home and would be dropped on round-trip.
    # This is also the server-owned-field guard for PUT /v1/workflow bodies.
    with pytest.raises(WorkflowValidationError, match="unknown top-level key: 'version'"):
        workflow_from_document({"states": ["a"], "transitions": [], "version": 2})


def test_from_document_rejects_duplicate_pairs() -> None:
    document = {
        "states": ["a", "b"],
        "transitions": [{"name": "Go", "from": "a", "to": "b"}, {"name": "Rush", "from": "a", "to": "b"}],
    }

    with pytest.raises(WorkflowValidationError, match="duplicate transition"):
        workflow_from_document(document)


def test_from_document_rejects_unknown_state_references() -> None:
    document = {"states": ["a", "b"], "transitions": [{"name": "Go", "from": "a", "to": "ghost"}]}

    with pytest.raises(WorkflowValidationError, match="unknown state 'ghost'"):
        workflow_from_document(document)


def test_validator_collects_all_errors_at_once() -> None:
    document = {
        "states": ["a", "a", 3],
        "transitions": [{"name": "", "from": "a", "to": "ghost"}, {"from": "a", "to": "a"}],
    }

    with pytest.raises(WorkflowValidationError) as exc_info:
        workflow_from_document(document)

    errors = exc_info.value.errors
    assert any("duplicate state 'a'" in e for e in errors)
    assert any("must be a string or an object" in e for e in errors)
    assert any("'name' cannot be empty" in e for e in errors)
    assert any("unknown state 'ghost'" in e for e in errors)
    assert any("missing field(s) 'name'" in e for e in errors)
    assert len(errors) == 5


def test_from_document_rejects_unreachable_states() -> None:
    document = {"states": ["a", "b", "orphan"], "transitions": [{"name": "Go", "from": "a", "to": "b"}]}

    with pytest.raises(WorkflowValidationError, match="'orphan' is unreachable"):
        workflow_from_document(document)


def test_reachability_considers_all_entry_states() -> None:
    # c is reachable only from the second entry state — still a valid workflow.
    document = {
        "states": [{"name": "a", "initial": True}, {"name": "b", "initial": True}, "c"],
        "transitions": [{"name": "Go", "from": "b", "to": "c"}],
    }

    workflow = workflow_from_document(document)

    assert workflow.unreachable_states() == set()


def test_validation_error_is_an_enveloped_app_error() -> None:
    """The ported error must ride the central handler, never a bare 500."""
    error = WorkflowValidationError(["problem one", "problem two"])

    assert isinstance(error, ValidationError)
    assert error.error_code is ErrorCode.INVALID_WORKFLOW_DEFINITION
    assert error.details == {"errors": ["problem one", "problem two"]}
    assert error.errors == ["problem one", "problem two"]
