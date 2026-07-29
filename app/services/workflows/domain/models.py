"""Domain model: the value objects a workflow definition is made of."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Final

RESERVED_TRANSITION_FIELDS: Final[frozenset[str]] = frozenset({"name", "from", "to"})
RESERVED_STATE_FIELDS: Final[frozenset[str]] = frozenset({"name", "initial"})

# State-meta key marking task completion. Defined here — with the document
# vocabulary — so the seed (own feature) and the tasks feature (sibling-domain
# allowance) share one spelling. Workflow machinery itself never reads it.
COMPLETES_META_KEY: Final[str] = "completes"


def require_nonblank(value: str, label: str) -> None:
    """Raise ``ValueError`` unless ``value`` has visible content. The single
    home of the "everything has a name" rule: value objects enforce it at
    construction and the document boundary calls it for positional reporting."""
    if not value.strip():
        raise ValueError(f"{label} cannot be empty")


def _freeze_meta(instance: Any, reserved: frozenset[str]) -> None:
    """Shared ``__post_init__`` tail: guard reserved collisions, wrap meta read-only.

    ``meta`` is excluded from the generated ``__hash__`` (see the field
    definitions) because mappings are unhashable; equality still compares it.
    """
    clash = reserved & instance.meta.keys()
    if clash:
        raise ValueError(f"meta keys collide with core fields: {sorted(clash)}")
    object.__setattr__(instance, "meta", MappingProxyType(dict(instance.meta)))


@dataclass(frozen=True, slots=True)
class State:
    """A named state/column with properties.

    ``initial`` marks a legal entry point: new work items may start here.
    ``meta`` carries use-case extensions (column color, ``completes`` marker,
    ...) that the workflow machinery itself never interprets, mirroring
    ``Transition.meta``. In a document a bare string is shorthand for a state
    with no properties.
    """

    name: str
    initial: bool = False
    meta: Mapping[str, Any] = field(default_factory=dict[str, Any], hash=False)

    def __post_init__(self) -> None:
        require_nonblank(self.name, "State name")
        _freeze_meta(self, RESERVED_STATE_FIELDS)


@dataclass(frozen=True, slots=True)
class Transition:
    """A named, directed edge between two states (Jira's "Start Progress").

    ``meta`` carries use-case extensions (button color, required role, ...)
    that travel with the definition but which the machinery itself never
    interprets. Keys must not collide with the core document fields. The
    mapping is wrapped read-only at construction, so the value object is
    deeply immutable.
    """

    name: str
    from_state: str
    to_state: str
    meta: Mapping[str, Any] = field(default_factory=dict[str, Any], hash=False)

    def __post_init__(self) -> None:
        require_nonblank(self.name, "Transition name")
        _freeze_meta(self, RESERVED_TRANSITION_FIELDS)


type StatePair = tuple[str, str]
type TransitionTable = dict[StatePair, Transition]
