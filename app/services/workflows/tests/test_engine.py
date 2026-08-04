"""Unit tests for WorkflowEngine — the state-machine rules any consumer drives."""

import pytest

from app.core.errors import (
    InvalidTransitionError,
    TransitionForbiddenError,
    UnknownStatusError,
    WipLimitExceededError,
)
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.engine import TransitionContext, WorkflowEngine
from app.services.workflows.domain.models import State

# The empty context: no roles, no occupancy — enforces nothing beyond move legality.
NO_CTX = TransitionContext()


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


def _guarded() -> Workflow:
    """A role guard on a transition and a WIP limit on a state."""
    workflow = Workflow(
        states=[
            State("new", initial=True),
            State("review", meta={"wip_limit": 1}),
            State("done", meta={"completes": True}),
        ]
    )
    workflow.allow_transition("Submit", from_state="new", to_state="review")
    workflow.allow_transition("Approve", from_state="review", to_state="done", roles=["manager"])
    return workflow


@pytest.fixture
def engine() -> WorkflowEngine:
    return WorkflowEngine(_strict())


@pytest.fixture
def guarded() -> WorkflowEngine:
    return WorkflowEngine(_guarded())


class TestResolveEntry:
    def test_none_resolves_to_default_entry(self, engine: WorkflowEngine) -> None:
        assert engine.resolve_entry(None, context=NO_CTX) == "new"

    def test_known_entry_state_is_returned(self, engine: WorkflowEngine) -> None:
        assert engine.resolve_entry("new", context=NO_CTX) == "new"

    def test_known_non_entry_state_raises_invalid_transition(self, engine: WorkflowEngine) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            engine.resolve_entry("completed", context=NO_CTX)
        assert exc.value.details == {"from": None, "to": "completed", "allowed": ["new"]}

    def test_unknown_state_raises_unknown_status(self, engine: WorkflowEngine) -> None:
        with pytest.raises(UnknownStatusError) as exc:
            engine.resolve_entry("ghost", context=NO_CTX)
        assert exc.value.details == {
            "field": "status",
            "value": "ghost",
            "known_states": ["new", "in_progress", "completed"],
        }

    def test_create_into_a_full_entry_state_is_refused(self) -> None:
        workflow = Workflow(states=[State("backlog", initial=True, meta={"wip_limit": 2})])
        engine = WorkflowEngine(workflow)
        with pytest.raises(WipLimitExceededError) as exc:
            engine.resolve_entry("backlog", context=TransitionContext(occupancy={"backlog": 2}))
        assert exc.value.details == {"state": "backlog", "limit": 2, "current": 2}


class TestCheckMove:
    def test_same_state_is_a_no_move(self, engine: WorkflowEngine) -> None:
        engine.check_move("new", "new", context=NO_CTX)  # must not raise

    def test_legal_move_passes(self, engine: WorkflowEngine) -> None:
        engine.check_move("new", "in_progress", context=NO_CTX)  # must not raise

    def test_illegal_move_raises_with_sorted_allowed(self, engine: WorkflowEngine) -> None:
        with pytest.raises(InvalidTransitionError) as exc:
            engine.check_move("new", "completed", context=NO_CTX)
        assert exc.value.details == {"from": "new", "to": "completed", "allowed": ["in_progress"]}

    def test_unknown_target_raises_unknown_status(self, engine: WorkflowEngine) -> None:
        with pytest.raises(UnknownStatusError):
            engine.check_move("new", "ghost", context=NO_CTX)


class TestRoleGuard:
    def test_actor_with_a_required_role_may_transition(self, guarded: WorkflowEngine) -> None:
        guarded.check_move("review", "done", context=TransitionContext(roles=frozenset({"manager"})))

    def test_actor_without_a_required_role_is_forbidden(self, guarded: WorkflowEngine) -> None:
        with pytest.raises(TransitionForbiddenError) as exc:
            guarded.check_move("review", "done", context=TransitionContext(roles=frozenset({"dev"})))
        assert exc.value.details == {
            "transition": "Approve",
            "required_roles": ["manager"],
            "actor_roles": ["dev"],
        }

    def test_unguarded_transition_ignores_roles(self, guarded: WorkflowEngine) -> None:
        # "Submit" (new -> review) declares no roles — a role-less actor may make it.
        guarded.check_move("new", "review", context=NO_CTX)

    def test_role_is_checked_before_capacity(self) -> None:
        # A move that is both role-guarded and into a full state surfaces the 403, not the 409.
        workflow = Workflow(states=[State("a", initial=True), State("b", meta={"wip_limit": 0})])
        workflow.allow_transition("Go", from_state="a", to_state="b", roles=["admin"])
        engine = WorkflowEngine(workflow)
        with pytest.raises(TransitionForbiddenError):
            engine.check_move("a", "b", context=TransitionContext(occupancy={"b": 0}))


class TestWipLimit:
    def test_entering_below_the_limit_passes(self, guarded: WorkflowEngine) -> None:
        guarded.check_move("new", "review", context=TransitionContext(occupancy={"review": 0}))

    def test_entering_at_the_limit_is_refused(self, guarded: WorkflowEngine) -> None:
        with pytest.raises(WipLimitExceededError) as exc:
            guarded.check_move("new", "review", context=TransitionContext(occupancy={"review": 1}))
        assert exc.value.details == {"state": "review", "limit": 1, "current": 1}

    def test_same_state_no_move_skips_the_wip_check(self, guarded: WorkflowEngine) -> None:
        # "review" is over its limit, but a same-state write enters nothing, so it is allowed.
        guarded.check_move("review", "review", context=TransitionContext(occupancy={"review": 5}))

    def test_leaving_a_full_state_is_allowed(self, guarded: WorkflowEngine) -> None:
        # "review" is full, but moving *out* to "done" (unlimited) is fine.
        guarded.check_move(
            "review", "done", context=TransitionContext(roles=frozenset({"manager"}), occupancy={"review": 9})
        )


class TestCompletes:
    def test_true_when_state_carries_completes_meta(self, engine: WorkflowEngine) -> None:
        assert engine.completes("completed") is True

    def test_false_when_state_has_no_completes_meta(self, engine: WorkflowEngine) -> None:
        assert engine.completes("new") is False


class TestNeedsOccupancy:
    def test_true_when_entering_a_capped_state(self, guarded: WorkflowEngine) -> None:
        assert guarded.needs_occupancy(from_status="new", to_status="review") is True

    def test_false_when_entering_an_uncapped_state(self, guarded: WorkflowEngine) -> None:
        # A capped state elsewhere in the definition must not make every move pay for a count.
        assert guarded.needs_occupancy(from_status="review", to_status="done") is False

    def test_false_for_a_same_state_write(self, guarded: WorkflowEngine) -> None:
        assert guarded.needs_occupancy(from_status="review", to_status="review") is False

    def test_false_for_an_unknown_target(self, guarded: WorkflowEngine) -> None:
        # ``check_move``/``resolve_entry`` refuse it with 422; no count could change that.
        assert guarded.needs_occupancy(from_status="new", to_status="ghost") is False

    def test_none_target_resolves_to_the_default_entry(self, guarded: WorkflowEngine) -> None:
        # A create with no status enters ``default_entry`` ("new"), which carries no limit.
        assert guarded.needs_occupancy(from_status=None, to_status=None) is False

    def test_true_when_a_create_names_a_capped_entry_state(self) -> None:
        workflow = Workflow(states=[State("backlog", initial=True, meta={"wip_limit": 2})])
        assert WorkflowEngine(workflow).needs_occupancy(from_status=None, to_status="backlog") is True

    def test_false_when_no_state_declares_a_wip_limit(self, engine: WorkflowEngine) -> None:
        assert engine.needs_occupancy(from_status="new", to_status="in_progress") is False


class TestLegalMovesAndDefaultEntry:
    def test_default_entry_exposes_first_entry_state(self, engine: WorkflowEngine) -> None:
        assert engine.default_entry == "new"

    def test_legal_moves_lists_leaving_transitions(self, engine: WorkflowEngine) -> None:
        moves = engine.legal_moves("new")
        assert [(t.name, t.to_state) for t in moves] == [("Start work", "in_progress")]

    def test_legal_moves_empty_for_terminal_state(self, engine: WorkflowEngine) -> None:
        assert engine.legal_moves("completed") == []
