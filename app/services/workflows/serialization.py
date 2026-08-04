"""Document (de)serialization for workflow definitions.

Kept out of the domain on purpose: ``definition.Workflow`` knows nothing about
wire formats; this module depends on the domain, never the reverse. Documents
are plain dicts — the JSON column and the HTTP boundary both speak them
natively, so no string layer exists here.

Validation is layered: structural problems (not an object, missing lists)
abort immediately because nothing after them is checkable; content problems
(bad states, bad transitions) accumulate so the caller sees every error in
one pass.
"""

from typing import Any, cast

from app.services.workflows.domain.definition import Workflow
from app.services.workflows.domain.models import (
    RESERVED_STATE_FIELDS,
    RESERVED_TRANSITION_FIELDS,
    ROLES_META_KEY,
    WIP_LIMIT_META_KEY,
    State,
    Transition,
    TransitionTable,
    require_nonblank,
)
from app.services.workflows.errors import WorkflowValidationError


def workflow_to_document(workflow: Workflow) -> dict[str, Any]:
    transitions = [
        {"name": transition.name, "from": transition.from_state, "to": transition.to_state}
        | dict(sorted(transition.meta.items()))
        for _, transition in sorted(workflow.transitions.items())
    ]
    states = [_state_entry(state) for state in workflow.states]
    return {"states": states, "transitions": transitions}


def _state_entry(state: State) -> str | dict[str, Any]:
    """Emit the string shorthand when a state has no properties."""
    if not state.initial and not state.meta:
        return state.name
    entry: dict[str, Any] = {"name": state.name}
    if state.initial:
        entry["initial"] = True
    return entry | dict(sorted(state.meta.items()))


def workflow_from_document(data: object) -> Workflow:
    """Parse and validate a definition document, collecting ALL problems at once.

    Any invalid input — wrong shape, missing/mistyped fields, blank names,
    duplicate states or pairs, transitions referencing undefined states —
    raises a single ``WorkflowValidationError`` listing every error found.
    """
    document = _parse_document(data)
    errors: list[str] = []
    states = _parse_states(document["states"], errors)
    transitions = _parse_transitions(document["transitions"], {s.name for s in states}, errors)
    if errors:
        raise WorkflowValidationError(errors)
    try:
        workflow = Workflow(states=states, transitions=transitions)
    except ValueError as e:  # safety net: domain rules added later can't slip through
        raise WorkflowValidationError([str(e)]) from e
    unreachable = workflow.unreachable_states()
    if unreachable:
        entries = workflow.entry_states
        raise WorkflowValidationError(
            [f"state {s!r} is unreachable from entry states {entries}" for s in sorted(unreachable)]
        )
    return workflow


def _parse_document(data: object) -> dict[str, Any]:
    """Structural layer: guard clauses, abort on the first unrecoverable shape problem."""
    if not isinstance(data, dict):
        raise WorkflowValidationError(["document must be a JSON object"])
    document = cast(dict[str, Any], data)
    problems = [
        f"'{key}' must be a list" for key in ("states", "transitions") if not isinstance(document.get(key), list)
    ]
    # Unlike state/transition entries, top-level extras have no meta home and
    # would be silently dropped on round-trip — reject them. This is also what
    # rejects server-owned fields (``version``, ``created_at``) in PUT bodies.
    problems += [f"unknown top-level key: {key!r}" for key in sorted(set(document) - {"states", "transitions"})]
    if problems:
        raise WorkflowValidationError(problems)
    return document


def _parse_states(raw_states: list[Any], errors: list[str]) -> list[State]:
    if not raw_states:
        errors.append("'states' must contain at least one state")
    states: list[State] = []
    seen: set[str] = set()
    for i, entry in enumerate(raw_states):
        state = _parse_state(i, entry, errors)
        if state is None:
            continue
        if state.name in seen:
            errors.append(f"states[{i}]: duplicate state {state.name!r}")
            continue
        seen.add(state.name)
        states.append(state)
    return states


def _extract_meta(entry: dict[str, Any], reserved: frozenset[str]) -> dict[str, Any]:
    """The open content model: every key that is not a core field is meta."""
    return {key: value for key, value in entry.items() if key not in reserved}


def _wip_limit_error(meta: dict[str, Any]) -> str | None:
    """The engine-interpreted ``wip_limit`` guard must be a non-negative int (``bool`` excluded —
    it is an ``int`` subclass). Absent ⇒ no limit. Validated here so a bad limit fails at
    definition time, not as a 500 on a later task write."""
    if WIP_LIMIT_META_KEY not in meta:
        return None
    limit = meta[WIP_LIMIT_META_KEY]
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        return f"{WIP_LIMIT_META_KEY!r} must be a non-negative integer"
    return None


def _roles_error(meta: dict[str, Any]) -> str | None:
    """The engine-interpreted ``roles`` guard must be a non-empty list of non-empty strings.
    Absent ⇒ no guard (omit it rather than spelling an empty list)."""
    if ROLES_META_KEY not in meta:
        return None
    roles = meta[ROLES_META_KEY]
    message = f"{ROLES_META_KEY!r} must be a non-empty list of non-empty strings"
    if not isinstance(roles, list):
        return message
    items = cast(list[Any], roles)
    if not items or not all(isinstance(item, str) and item.strip() for item in items):
        return message
    return None


def _parse_state(i: int, entry: Any, errors: list[str]) -> State | None:
    """A state is a string (shorthand) or an object with name/initial/meta.

    Name rules (non-blank, ...) are owned by ``State.__post_init__`` — the
    constructor is the validator, so the rule cannot drift between layers.
    """
    match entry:
        case str():
            name, initial, meta = entry, False, {}
        case {"name": str() as name}:
            initial = entry.get("initial", False)
            if not isinstance(initial, bool):
                errors.append(f"states[{i}]: 'initial' must be a boolean")
                return None
            meta = _extract_meta(entry, RESERVED_STATE_FIELDS)
            wip_error = _wip_limit_error(meta)
            if wip_error is not None:
                errors.append(f"states[{i}]: {wip_error}")
                return None
        case dict():
            errors.append(f"states[{i}]: object form requires a non-empty string 'name'")
            return None
        case _:
            errors.append(f"states[{i}]: must be a string or an object, got {type(entry).__name__}")
            return None
    try:
        return State(name, initial=initial, meta=meta)
    except ValueError as e:
        errors.append(f"states[{i}]: {e}")
        return None


def _parse_transitions(raw_transitions: list[Any], known: set[str], errors: list[str]) -> TransitionTable:
    parsed: TransitionTable = {}
    for i, entry in enumerate(raw_transitions):
        fields = _transition_fields(i, entry, errors)
        if fields is None:
            continue
        name, from_state, to_state, meta = fields
        problems = _transition_rule_errors(i, name, from_state, to_state, known, parsed)
        roles_error = _roles_error(meta)
        if roles_error is not None:
            problems.append(f"transitions[{i}]: {roles_error}")
        if problems:
            errors.extend(problems)
            continue
        try:
            parsed[(from_state, to_state)] = Transition(name, from_state, to_state, meta)
        except ValueError as e:  # safety net: model rules added later can't slip through
            errors.append(f"transitions[{i}]: {e}")
    return parsed


def _transition_fields(i: int, entry: Any, errors: list[str]) -> tuple[str, str, str, dict[str, Any]] | None:
    """Shape layer: an object with string name/from/to; any other keys collect as meta."""
    match entry:
        case {"name": str() as name, "from": str() as from_state, "to": str() as to_state}:
            return name, from_state, to_state, _extract_meta(entry, RESERVED_TRANSITION_FIELDS)
        case dict():
            missing = [f for f in ("name", "from", "to") if f not in entry]
            if missing:
                errors.append(f"transitions[{i}]: missing field(s) {', '.join(repr(m) for m in missing)}")
            else:
                bad = [f for f in ("name", "from", "to") if not isinstance(entry[f], str)]
                errors.append(f"transitions[{i}]: field(s) {', '.join(repr(b) for b in bad)} must be strings")
            return None
        case _:
            errors.append(f"transitions[{i}]: must be an object, got {type(entry).__name__}")
            return None


def _transition_rule_errors(
    i: int, name: str, from_state: str, to_state: str, known: set[str], parsed: TransitionTable
) -> list[str]:
    """Rule layer: a well-shaped entry must also make sense against the states."""
    problems: list[str] = []
    try:
        require_nonblank(name, "'name'")  # the shared predicate, reported positionally
    except ValueError as e:
        problems.append(f"transitions[{i}]: {e}")
    for fieldname, value in (("from", from_state), ("to", to_state)):
        if value not in known:
            problems.append(f"transitions[{i}]: {fieldname!r} references unknown state {value!r}")
    if (from_state, to_state) in parsed:
        problems.append(f"transitions[{i}]: duplicate transition {from_state} -> {to_state}")
    return problems
