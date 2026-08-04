"""The workflow engine: applies an active definition's rules to status decisions.

One engine wraps one ``Workflow``; any feature that stores workflow-governed
status drives it (tasks today). The engine owns the state-machine taxonomy —
entry resolution, move legality, completion, and the ``meta``-declared guards
(role guards on transitions, WIP limits on states) — so consumers stay thin and
a second consumer inherits identical enforcement instead of re-deriving it.

Guards need runtime facts the definition does not hold (who the actor is, how
full each state is), so the caller passes a ``TransitionContext`` per decision.
Enforcement errors live in ``app.core.errors`` (not a feature ``errors.py``):
this is domain, and the domain layer may import ``app/core`` but not a
feature-root ``errors.py``. See ``InvalidTransitionError`` for the rationale.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from app.core.errors import (
    InvalidTransitionError,
    TransitionForbiddenError,
    UnknownStatusError,
    WipLimitExceededError,
)
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import (
    COMPLETES_META_KEY,
    ROLES_META_KEY,
    WIP_LIMIT_META_KEY,
    Transition,
)


@dataclass(frozen=True, slots=True)
class TransitionContext:
    """The runtime facts guards need, supplied by the caller per status decision:

    - ``roles``: the acting caller's roles — checked against a transition's ``roles`` guard.
    - ``occupancy``: current work-item count per status — checked against a state's ``wip_limit``.

    Both default to empty (an anonymous actor / no occupancy known), which enforces nothing
    beyond the definition's own move legality.
    """

    roles: frozenset[str] = frozenset()
    occupancy: Mapping[str, int] = field(default_factory=dict[str, int])


class WorkflowEngine:
    __slots__ = ("_workflow",)

    def __init__(self, workflow: Workflow) -> None:
        self._workflow = workflow

    @property
    def default_entry(self) -> str:
        """Where new work items start unless the caller picks another entry state."""
        return self._workflow.default_entry

    def needs_occupancy(self, *, from_status: str | None, to_status: str | None) -> bool:
        """Whether a write needs per-status occupancy: only when it *enters* a state that
        declares a ``wip_limit``. ``from_status=None`` is a create; ``to_status=None`` means
        the default entry. Same-state writes enter nothing, and an unknown target is refused
        by the move check anyway — neither can fire a limit, so neither needs the count.

        The engine owns this because it owns what "entering a state" means; a caller that
        re-derived it would silently stop fetching occupancy the day that rule changes.
        """
        target = self.default_entry if to_status is None else to_status
        if target == from_status or target not in self._workflow.state_names:
            return False
        return WIP_LIMIT_META_KEY in self._workflow.state(target).meta

    def resolve_entry(self, status: str | None, *, context: TransitionContext) -> str:
        """The create-time status: the default entry, or a caller-chosen entry state. A create
        enters a state, so it is WIP-checked; it is not a transition, so no role guard applies."""
        resolved = self._entry_state(status)
        self._check_wip(resolved, context)
        return resolved

    def _entry_state(self, status: str | None) -> str:
        """The state a create lands in, or the reason it cannot."""
        if status is None:
            return self.default_entry
        self._require_known(status)
        entries = self._workflow.entry_states
        if status not in entries:
            raise InvalidTransitionError(details={"from": None, "to": status, "allowed": entries})
        return status

    def check_move(self, from_status: str, to_status: str, *, context: TransitionContext) -> None:
        """Raise unless ``from_status -> to_status`` is legal *and* permitted. Same-state writes
        are no-moves (they enter nothing, so neither guard applies)."""
        self._require_known(to_status)
        if to_status == from_status:
            return
        transition = self._workflow.transition_between(from_status, to_status)
        if transition is None:
            raise InvalidTransitionError(
                details={
                    "from": from_status,
                    "to": to_status,
                    "allowed": sorted(self._workflow.moves_from(from_status)),
                }
            )
        self._check_role(transition, context)
        self._check_wip(to_status, context)

    def completes(self, status: str) -> bool:
        """Whether entering ``status`` marks completion (state meta ``completes``)."""
        return bool(self._workflow.state(status).meta.get(COMPLETES_META_KEY))

    def legal_moves(self, status: str) -> list[Transition]:
        """Transitions leaving ``status`` — what a UI renders as buttons."""
        return self._workflow.transitions_from(status)

    def _check_role(self, transition: Transition, context: TransitionContext) -> None:
        """A transition's ``roles`` guard: the actor must hold at least one. Authorization is
        checked before capacity, so a caller who may not move at all learns that first."""
        required = transition.meta.get(ROLES_META_KEY)
        if required and context.roles.isdisjoint(required):
            raise TransitionForbiddenError(
                details={
                    "transition": transition.name,
                    "required_roles": sorted(required),
                    "actor_roles": sorted(context.roles),
                }
            )

    def _check_wip(self, state: str, context: TransitionContext) -> None:
        """A state's ``wip_limit``: refuse entry when it is already full. Best-effort — the
        occupancy read is not serialized against concurrent writers (see TIS §8.8)."""
        limit = self._workflow.state(state).meta.get(WIP_LIMIT_META_KEY)
        if limit is None:
            return
        current = context.occupancy.get(state, 0)
        if current >= limit:
            raise WipLimitExceededError(details={"state": state, "limit": limit, "current": current})

    def _require_known(self, status: str) -> None:
        """A status that is no state of the workflow is an unknown-status error, not a refusal."""
        if status not in self._workflow.state_names:
            raise UnknownStatusError(
                details={"field": "status", "value": status, "known_states": self._workflow.state_names}
            )
