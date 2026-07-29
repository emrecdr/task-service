"""Value objects: construction rules, immutability, hashability."""

import pytest

from app.services.workflows.domain.models import State, Transition


def test_transition_requires_a_name() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        Transition("   ", "a", "b")


def test_transition_is_immutable() -> None:
    transition = Transition("Go", "a", "b")

    with pytest.raises(AttributeError):
        transition.name = "Stop"  # type: ignore[misc]


def test_meta_keys_cannot_shadow_core_fields() -> None:
    with pytest.raises(ValueError, match="collide with core fields"):
        Transition("Go", "a", "b", meta={"from": "x"})


def test_meta_mapping_is_read_only() -> None:
    transition = Transition("Go", "a", "b", meta={"color": "#00f"})

    with pytest.raises(TypeError):
        transition.meta["color"] = "red"  # type: ignore[index]


def test_state_requires_a_name_and_guards_meta() -> None:
    with pytest.raises(ValueError, match="name cannot be empty"):
        State("   ")
    with pytest.raises(ValueError, match="collide with core fields"):
        State("a", meta={"initial": True})


def test_value_objects_are_hashable_despite_meta() -> None:
    # meta is excluded from __hash__ (mappings are unhashable) but kept in eq.
    assert hash(State("a")) == hash(State("a"))
    assert {State("a"), State("a")} == {State("a")}
    assert State("a", meta={"x": 1}) != State("a", meta={"x": 2})  # eq still sees meta
    assert hash(Transition("Go", "a", "b", meta={"color": "#00f"})) == hash(Transition("Go", "a", "b"))
