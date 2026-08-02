"""The workflow engine: applies an active definition's rules to status decisions.

One engine wraps one ``Workflow``; any feature that stores workflow-governed
status drives it (tasks today). The engine owns the state-machine taxonomy —
entry resolution, move legality, completion — so consumers stay thin and a
second consumer inherits identical enforcement instead of re-deriving it.

Enforcement errors live in ``app.core.errors`` (not a feature ``errors.py``):
this is domain, and the domain layer may import ``app/core`` but not a
feature-root ``errors.py``. See ``InvalidTransitionError`` for the rationale.
"""

from app.core.errors import InvalidTransitionError, UnknownStatusError
from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import COMPLETES_META_KEY, Transition


class WorkflowEngine:
    __slots__ = ("_workflow",)

    def __init__(self, workflow: Workflow) -> None:
        self._workflow = workflow

    @property
    def default_entry(self) -> str:
        """Where new work items start unless the caller picks another entry state."""
        return self._workflow.default_entry

    def resolve_entry(self, status: str | None) -> str:
        """The create-time status: the default entry, or a caller-chosen entry state."""
        if status is None:
            return self.default_entry
        self._require_known(status)
        entries = self._workflow.entry_states
        if status not in entries:
            raise InvalidTransitionError(details={"from": None, "to": status, "allowed": entries})
        return status

    def check_move(self, from_status: str, to_status: str) -> None:
        """Raise unless ``from_status -> to_status`` is legal. Same-state writes are no-moves."""
        self._require_known(to_status)
        if to_status == from_status:
            return
        if self._workflow.transition_between(from_status, to_status) is None:
            raise InvalidTransitionError(
                details={
                    "from": from_status,
                    "to": to_status,
                    "allowed": sorted(self._workflow.moves_from(from_status)),
                }
            )

    def completes(self, status: str) -> bool:
        """Whether entering ``status`` marks completion (state meta ``completes``)."""
        return bool(self._workflow.state(status).meta.get(COMPLETES_META_KEY))

    def legal_moves(self, status: str) -> list[Transition]:
        """Transitions leaving ``status`` — what a UI renders as buttons."""
        return self._workflow.transitions_from(status)

    def _require_known(self, status: str) -> None:
        """A status that is no state of the workflow is an unknown-status error, not a refusal."""
        if status not in self._workflow.state_names:
            raise UnknownStatusError(
                details={"field": "status", "value": status, "known_states": self._workflow.state_names}
            )
