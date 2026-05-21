import pytest

from app.services.tasks.constants import Status
from app.services.tasks.domain.models import Task


def _new(**overrides: object) -> Task:
    base: dict[str, object] = {
        "title": "alpha",
        "description": "d",
        "status": Status.NEW,
        "priority": 3,
    }
    base.update(overrides)
    return Task.from_input(**base)  # type: ignore[arg-type]


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


class TestApplyReplace:
    def test_overwrites_all_mutable_fields_and_recomputes_title_key(self) -> None:
        task = _new(title="orig", description="d1", status=Status.NEW, priority=1)
        task.apply_replace(title="  Renamed  ", description="d2", status=Status.IN_PROGRESS, priority=5)
        assert task.title == "Renamed"
        assert task.title_key == "renamed"
        assert task.description == "d2"
        assert task.status is Status.IN_PROGRESS
        assert task.priority == 5

    def test_rejects_empty_title(self) -> None:
        task = _new()
        with pytest.raises(ValueError, match="empty"):
            task.apply_replace(title="   ", description=None, status=Status.NEW, priority=1)

    def test_clears_description_when_set_to_none(self) -> None:
        task = _new(description="present")
        task.apply_replace(title=task.title, description=None, status=task.status, priority=task.priority)
        assert task.description is None


class TestApplyPatch:
    def test_single_field_update(self) -> None:
        task = _new(priority=2)
        task.apply_patch({"priority": 5})
        assert task.priority == 5
        assert task.title == "alpha"  # untouched

    def test_multi_field_update_in_one_pass(self) -> None:
        task = _new(title="orig", description="d1", status=Status.NEW, priority=1)
        task.apply_patch({"title": "  Renamed  ", "status": Status.IN_PROGRESS, "priority": 4})
        assert task.title == "Renamed"
        assert task.title_key == "renamed"
        assert task.status is Status.IN_PROGRESS
        assert task.priority == 4
        assert task.description == "d1"

    def test_title_field_recomputes_title_key(self) -> None:
        task = _new(title="orig")
        task.apply_patch({"title": " FRESH "})
        assert task.title == "FRESH"
        assert task.title_key == "fresh"

    def test_title_field_rejects_empty(self) -> None:
        task = _new()
        with pytest.raises(ValueError, match="empty"):
            task.apply_patch({"title": "   "})

    def test_unknown_field_raises_value_error(self) -> None:
        task = _new()
        with pytest.raises(ValueError, match="unknown patch fields"):
            task.apply_patch({"id": 999})

    def test_unknown_field_named_in_error(self) -> None:
        task = _new()
        with pytest.raises(ValueError, match=r"\['created_at'\]"):
            task.apply_patch({"created_at": "2020-01-01T00:00:00Z"})


class TestSnapshot:
    def test_returns_detached_revalidated_copy(self) -> None:
        original = _new(title="alpha", priority=3)
        snapshot = original.snapshot()
        assert snapshot is not original
        assert snapshot.title == original.title
        assert snapshot.priority == original.priority
        assert snapshot.title_key == original.title_key

    def test_mutating_original_does_not_affect_snapshot(self) -> None:
        original = _new(priority=3)
        snapshot = original.snapshot()
        original.apply_patch({"priority": 5})
        assert original.priority == 5
        assert snapshot.priority == 3

    def test_snapshot_preserves_id_when_set(self) -> None:
        original = _new()
        original.id = 42
        snapshot = original.snapshot()
        assert snapshot.id == 42
