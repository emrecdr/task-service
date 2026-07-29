"""The workflow definition: which states exist and which named moves are legal.

States and transitions are data — the machine's shape is owned by users at
runtime, not by code. The trade-off: pyright cannot catch a typo'd state, so
everything is validated here at runtime. Serialization lives in the feature
root's ``serialization.py``; this module never imports it (dependency
direction: the boundary depends on the domain, never the reverse).
"""

from collections.abc import Iterable, Mapping
from types import MappingProxyType
from typing import Any

from app.services.workflows.domain.models import State, StatePair, Transition, TransitionTable


class Workflow:
    """One workflow definition can serve many consumers.

    Deliberately not a dataclass: the state list and transition table are
    private, exposed only as read-only views, so the invariants checked at
    construction (unique states, transitions filed under matching keys over
    known endpoints) cannot be broken from outside afterwards. Edits go
    through ``allow_transition``, which re-checks the rules on every change.
    """

    __slots__ = ("_states", "_transitions")

    def __init__(self, states: Iterable[State], transitions: TransitionTable | None = None) -> None:
        self._states = list(states)
        self._transitions = dict(transitions) if transitions else {}
        if not self._states:
            raise ValueError("Workflow needs at least one state")
        names = self.state_names
        known = set(names)
        if len(known) != len(names):
            raise ValueError("Duplicate states are not allowed")
        for key, transition in self._transitions.items():
            if key != (transition.from_state, transition.to_state):
                raise ValueError(f"Transition {transition.name!r} filed under wrong key {key!r}")
            for endpoint in key:
                if endpoint not in known:
                    raise ValueError(f"Unknown state: {endpoint!r}")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Workflow):
            return NotImplemented
        return self._states == other._states and self._transitions == other._transitions

    def __repr__(self) -> str:
        return f"Workflow(states={self._states!r}, transitions={self._transitions!r})"

    @property
    def states(self) -> tuple[State, ...]:
        """The states in column order, as a read-only snapshot."""
        return tuple(self._states)

    @property
    def transitions(self) -> Mapping[StatePair, Transition]:
        """The transition table as a live, read-only view."""
        return MappingProxyType(self._transitions)

    @property
    def state_names(self) -> list[str]:
        return [state.name for state in self._states]

    @property
    def entry_states(self) -> list[str]:
        """Where new work items may start: states marked ``initial``, or the first state."""
        marked = [state.name for state in self._states if state.initial]
        return marked or [self._states[0].name]

    @property
    def default_entry(self) -> str:
        """Where new work items start unless the caller picks another entry state."""
        return self.entry_states[0]

    def state(self, name: str) -> State:
        """The named state (with its ``meta``) — the single existence check."""
        for state in self._states:
            if state.name == name:
                return state
        raise ValueError(f"Unknown state: {name!r}")

    def require_state(self, name: str) -> None:
        """Raise ``ValueError`` unless ``name`` is a state of this workflow."""
        self.state(name)

    def allow_transition(self, name: str, *, from_state: str, to_state: str, **meta: Any) -> None:
        """Define a named legal move. Keyword-only direction: two positional
        state strings would swap silently (both are valid states either way)."""
        self.require_state(from_state)
        self.require_state(to_state)
        key = (from_state, to_state)
        if key in self._transitions:
            raise ValueError(f"Transition already defined for {from_state} -> {to_state}")
        self._transitions[key] = Transition(name, from_state, to_state, dict(meta))

    def transition_between(self, from_state: str, to_state: str) -> Transition | None:
        self.require_state(from_state)
        self.require_state(to_state)
        return self._transitions.get((from_state, to_state))

    def transitions_from(self, state: str) -> list[Transition]:
        """Full transitions leaving a state — what a UI renders as buttons."""
        self.require_state(state)
        return [transition for (from_, _), transition in self._transitions.items() if from_ == state]

    def moves_from(self, state: str) -> set[str]:
        return {transition.to_state for transition in self.transitions_from(state)}

    def unreachable_states(self) -> set[str]:
        """States with no path from any entry state (dead columns)."""
        # Deliberate precompute (not moves_from per pop): one O(E) pass over
        # the table instead of a full scan per visited state.
        adjacency: dict[str, set[str]] = {}
        for from_state, to_state in self._transitions:
            adjacency.setdefault(from_state, set()).add(to_state)
        reachable = set(self.entry_states)
        frontier = list(reachable)
        while frontier:
            for to_state in adjacency.get(frontier.pop(), ()):
                if to_state not in reachable:
                    reachable.add(to_state)
                    frontier.append(to_state)
        return set(self.state_names) - reachable
