"""``TagService`` use-cases: the in-use delete guard and the ``TagDeleted`` event.

Unit tests — an in-memory repo stands in for storage, so nothing here needs a database.
"""

import uuid
from collections.abc import Sequence

import pytest

from app.core.event_bus import Event
from app.services.tags.application.service import TagService
from app.services.tags.domain.events import TagDeleted
from app.services.tags.domain.models import Tag
from app.services.tags.errors import TagInUseError, TagNotFoundError
from app.services.tags.interfaces import TagRepositoryInterface


class FakeTagRepo(TagRepositoryInterface):
    """Stores tags and a per-tag usage count, and records what was removed."""

    def __init__(self, *, usage: dict[uuid.UUID, int] | None = None) -> None:
        self.tags: dict[uuid.UUID, Tag] = {}
        self.usage = usage or {}
        self.removed: list[Tag] = []
        self.events: list[Event] = []

    def add(self, name: str, *, used_by: int = 0) -> Tag:
        tag = Tag.from_name(name)
        self.tags[tag.id] = tag
        self.usage[tag.id] = used_by
        return tag

    async def resolve(self, names: Sequence[str]) -> dict[str, uuid.UUID]:
        raise NotImplementedError

    async def set_for_task(self, task_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]) -> None:
        raise NotImplementedError

    async def names_for_tasks(self, task_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        raise NotImplementedError

    async def task_ids_matching(self, name_keys: Sequence[str], *, match_all: bool) -> set[uuid.UUID]:
        raise NotImplementedError

    async def list_with_counts(self) -> list[tuple[Tag, int]]:
        return [(tag, self.usage.get(tag_id, 0)) for tag_id, tag in self.tags.items()]

    async def get(self, tag_id: uuid.UUID) -> Tag:
        try:
            return self.tags[tag_id]
        except KeyError as err:
            raise TagNotFoundError(details={"id": str(tag_id)}) from err

    async def task_count(self, tag_id: uuid.UUID) -> int:
        return self.usage.get(tag_id, 0)

    async def remove(self, tag: Tag, *, events: Sequence[Event]) -> None:
        del self.tags[tag.id]
        self.removed.append(tag)
        self.events.extend(events)


@pytest.fixture
def repo() -> FakeTagRepo:
    return FakeTagRepo()


@pytest.fixture
def service(repo: FakeTagRepo) -> TagService:
    return TagService(repo=repo)


class TestDelete:
    async def test_unused_tag_is_deleted_and_emits_tag_deleted(self, service: TagService, repo: FakeTagRepo) -> None:
        tag = repo.add("stale", used_by=0)

        await service.delete(tag.id)

        assert repo.removed == [tag]
        assert [type(e) for e in repo.events] == [TagDeleted]
        emitted = repo.events[0]
        assert isinstance(emitted, TagDeleted)
        assert (emitted.tag_id, emitted.name) == (tag.id, "stale")

    async def test_tag_in_use_is_refused_and_emits_nothing(self, service: TagService, repo: FakeTagRepo) -> None:
        tag = repo.add("urgent", used_by=3)

        with pytest.raises(TagInUseError) as err:
            await service.delete(tag.id)

        # The count is the point of the guard: it tells the caller what to untag first.
        assert err.value.details["task_count"] == 3
        assert err.value.details["name"] == "urgent"
        assert repo.removed == []
        assert repo.events == []

    async def test_unknown_tag_raises_not_found(self, service: TagService) -> None:
        with pytest.raises(TagNotFoundError):
            await service.delete(uuid.uuid7())


class TestList:
    async def test_reports_each_tag_with_its_usage_count(self, service: TagService, repo: FakeTagRepo) -> None:
        repo.add("urgent", used_by=2)
        repo.add("stale", used_by=0)

        listed = await service.list_tags()

        assert listed.total == 2
        assert {(item.name, item.task_count) for item in listed.items} == {("urgent", 2), ("stale", 0)}
