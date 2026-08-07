import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.event_bus import Event
from app.core.outbox import stage_events
from app.services.tags.domain.models import Tag, TaskTag
from app.services.tags.errors import TagNotFoundError
from app.services.tags.interfaces import TagRepositoryInterface


class SQLModelTagRepository(TagRepositoryInterface):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(self, names: Sequence[str]) -> dict[str, uuid.UUID]:
        # Normalise first so duplicates within one request collapse before they reach the DB:
        # ``["a", "A", " a "]`` is one tag because they share a name_key. The first spelling
        # wins, matching "the display form is whatever the caller first used".
        wanted: dict[str, str] = {}
        for name in names:
            _, name_key = Tag.clean_name(name)
            wanted.setdefault(name_key, name.strip())
        if not wanted:
            return {}

        rows = (await self._session.scalars(select(Tag).where(col(Tag.name_key).in_(wanted)))).all()
        resolved = {tag.name_key: tag.id for tag in rows}

        # Whatever is left has no tag yet; create it in the caller's transaction so tagging a
        # task and minting its tags commit together (FRD §2.7). ``Tag.id`` comes from a Python
        # default_factory, so the id is usable immediately — no flush needed to learn it.
        for name_key, display in wanted.items():
            if name_key not in resolved:
                tag = Tag(name=display, name_key=name_key)
                self._session.add(tag)
                resolved[name_key] = tag.id
        return resolved

    async def set_for_task(self, task_id: uuid.UUID, tag_ids: Sequence[uuid.UUID]) -> None:
        # Replace, never merge: clear the task's links then re-add. Deleting unconditionally
        # keeps this one statement rather than a diff, and the join carries no other state
        # that a rewrite could lose.
        #
        # Deliberately does NOT flush. On a create the caller stages tags before the task row
        # exists, and ``task_tags`` has an FK to ``tasks`` — flushing here would try to insert
        # the link first and fail. Leaving the rows pending lets the commit inside
        # ``TaskRepository.persist`` flush them, and SQLAlchemy's unit of work orders inserts
        # by FK dependency, so ``tasks`` lands before ``task_tags``. One transaction covers the
        # task, its tags and its outbox rows.
        await self._session.execute(delete(TaskTag).where(col(TaskTag.task_id) == task_id))
        for tag_id in dict.fromkeys(tag_ids):
            self._session.add(TaskTag(task_id=task_id, tag_id=tag_id))

    async def names_for_tasks(self, task_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
        if not task_ids:
            return {}
        stmt = (
            select(TaskTag.task_id, Tag.name)
            .join(Tag, col(Tag.id) == col(TaskTag.tag_id))
            .where(col(TaskTag.task_id).in_(task_ids))
            .order_by(col(Tag.name))
        )
        grouped: dict[uuid.UUID, list[str]] = {}
        for task_id, name in (await self._session.execute(stmt)).all():
            grouped.setdefault(task_id, []).append(name)
        return grouped

    async def task_ids_matching(self, name_keys: Sequence[str], *, match_all: bool) -> set[uuid.UUID]:
        if not name_keys:
            return set()
        distinct_keys = set(name_keys)
        stmt = (
            select(TaskTag.task_id)
            .join(Tag, col(Tag.id) == col(TaskTag.tag_id))
            .where(col(Tag.name_key).in_(distinct_keys))
        )
        if match_all:
            # The AND stays in SQL: a task qualifies when it matched every distinct key asked
            # for. Counting DISTINCT tag_id (not rows) keeps it correct regardless of joins.
            stmt = stmt.group_by(col(TaskTag.task_id)).having(
                func.count(func.distinct(col(TaskTag.tag_id))) == len(distinct_keys)
            )
        return set((await self._session.scalars(stmt)).all())

    async def list_with_counts(self) -> list[tuple[Tag, int]]:
        # Outer join so a tag no task holds still appears, with a count of zero — the list is
        # the vocabulary, and an unused tag is exactly the one an operator wants to delete.
        stmt = (
            select(Tag, func.count(col(TaskTag.task_id)))
            .outerjoin(TaskTag, col(TaskTag.tag_id) == col(Tag.id))
            .group_by(col(Tag.id))
            .order_by(col(Tag.name))
        )
        return [(tag, count) for tag, count in (await self._session.execute(stmt)).all()]

    async def get(self, tag_id: uuid.UUID) -> Tag:
        tag = await self._session.get(Tag, tag_id)
        if tag is None:
            raise TagNotFoundError(details={"id": str(tag_id)})
        return tag

    async def task_count(self, tag_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(TaskTag).where(col(TaskTag.tag_id) == tag_id)
        return (await self._session.scalars(stmt)).one()

    async def remove(self, tag: Tag, *, events: Sequence[Event]) -> None:
        await self._session.delete(tag)
        stage_events(self._session, events)
        await self._session.commit()
