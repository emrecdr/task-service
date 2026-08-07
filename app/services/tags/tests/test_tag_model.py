"""``Tag`` normalisation — the rule the whole feature's identity rests on (FRD §2.6)."""

import pytest

from app.services.tags.domain.models import Tag


@pytest.mark.parametrize(
    "raw",
    ["urgent", "Urgent", "URGENT", "  urgent  ", "\turgent\n"],
)
def test_names_differing_only_in_case_or_outer_space_share_a_key(raw: str) -> None:
    assert Tag.normalize_name(raw) == "urgent"


def test_inner_whitespace_is_significant() -> None:
    # Mirrors Task.title_key: only the outer edges are trimmed, so these are two tags.
    assert Tag.normalize_name("code review") != Tag.normalize_name("code  review")


def test_clean_name_keeps_the_display_form_verbatim() -> None:
    display, key = Tag.clean_name("  Code Review  ")
    assert display == "Code Review"
    assert key == "code review"


@pytest.mark.parametrize("blank", ["", "   ", "\t\n"])
def test_blank_names_are_rejected(blank: str) -> None:
    with pytest.raises(ValueError, match="must not be blank"):
        Tag.clean_name(blank)


def test_from_name_builds_both_forms() -> None:
    tag = Tag.from_name(" Backend ")
    assert (tag.name, tag.name_key) == ("Backend", "backend")
