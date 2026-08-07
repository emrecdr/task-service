import uuid

from app.services.tags.application.dto import TagListResponse, TagResponse
from app.services.tags.domain.events import TagDeleted
from app.services.tags.errors import TagInUseError
from app.services.tags.interfaces import TagRepositoryInterface


class TagService:
    """Use-cases over the tag vocabulary. Attaching tags to a task is *not* here — that runs
    through ``TaskService``, which owns the write the tags ride along with (FRD §2.7)."""

    def __init__(self, *, repo: TagRepositoryInterface) -> None:
        self._repo = repo

    async def list_tags(self) -> TagListResponse:
        rows = await self._repo.list_with_counts()
        items = [TagResponse.from_tag(tag, count) for tag, count in rows]
        return TagListResponse(items=items, total=len(items))

    async def delete(self, tag_id: uuid.UUID) -> None:
        """Delete a tag no task holds; refuse otherwise.

        The guard mirrors the workflow strand guard: refuse, report the count, let the caller
        decide — rather than silently untagging an unknown number of tasks.
        """
        tag = await self._repo.get(tag_id)
        in_use = await self._repo.task_count(tag_id)
        if in_use:
            raise TagInUseError(details={"id": str(tag_id), "name": tag.name, "task_count": in_use})
        await self._repo.remove(tag, events=[TagDeleted(tag_id=tag.id, name=tag.name)])
