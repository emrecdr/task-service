"""Unit tests for the Task domain entity."""

import pytest

from app.services.tasks.constants import Status
from app.services.tasks.domain.models import Task


class TestNormalizeTitle:
    def test_strips_outer_whitespace_and_casefolds(self) -> None:
        assert Task.normalize_title("  Fix Bug  ") == "fix bug"

    def test_inner_whitespace_is_significant(self) -> None:
        assert Task.normalize_title("Fix bug") != Task.normalize_title("Fix  bug")

    def test_collides_across_case_variants(self) -> None:
        for variant in ("Fix bug", "fix bug", " FIX BUG "):
            assert Task.normalize_title(variant) == "fix bug"


class TestFromInput:
    def test_builds_task_with_trimmed_title_and_normalized_key(self) -> None:
        task = Task.from_input(title="  Hello  ", description=None, status=Status.NEW, priority=3)
        assert task.title == "Hello"
        assert task.title_key == "hello"
        assert task.status is Status.NEW
        assert task.priority == 3

    def test_rejects_empty_title_after_trim(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            Task.from_input(title="   ", description=None, status=Status.NEW, priority=1)

    def test_preserves_original_title_verbatim_for_display(self) -> None:
        task = Task.from_input(title="Fix BUG", description=None, status=Status.NEW, priority=1)
        assert task.title == "Fix BUG"
        assert task.title_key == "fix bug"


class TestCreatedAt:
    def test_default_is_utc_timezone_aware(self) -> None:
        task = Task.from_input(title="x", description=None, status=Status.NEW, priority=1)
        assert task.created_at.tzinfo is not None
        offset = task.created_at.utcoffset()
        assert offset is not None
        assert offset.total_seconds() == 0
