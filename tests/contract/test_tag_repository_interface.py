"""Port conformance for ``TagRepositoryInterface`` — parametrized over every concrete impl.

These assert the contract the tasks feature relies on, not one adapter's internals: name_key
identity, replace-not-merge, batch reads, and the two ``?op=`` modes.
"""

import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from app.core import database
from app.services.tags.domain.models import Tag
from app.services.tags.errors import TagNotFoundError
from app.services.tags.infrastructure.repository import SQLModelTagRepository
from app.services.tags.interfaces import TagRepositoryInterface
from app.services.tasks.domain.models import Task
from sqlalchemy.ext.asyncio import AsyncSession

type SessionBuilder = Callable[[], AsyncSession]


def _sqlmodel_session() -> AsyncSession:
    return database.get_sessionmaker()()


SESSION_BUILDERS: list[SessionBuilder] = [_sqlmodel_session]


@pytest.fixture(params=SESSION_BUILDERS, ids=lambda builder: builder.__name__.lstrip("_"))
async def pair(request: pytest.FixtureRequest) -> AsyncIterator[tuple[TagRepositoryInterface, AsyncSession]]:
    session = request.param()
    try:
        yield SQLModelTagRepository(session), session
    finally:
        await session.close()


async def _task(session: AsyncSession, title: str) -> uuid.UUID:
    task = Task.from_input(title=title, description=None, status="new", priority=3)
    session.add(task)
    await session.flush()
    return task.id


async def test_resolve_creates_unknown_names_and_reuses_known_ones(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, _ = pair

    first = await repo.resolve(["alpha"])
    again = await repo.resolve(["alpha", "beta"])

    assert first["alpha"] == again["alpha"]  # same tag, not a second row
    assert set(again) == {"alpha", "beta"}


async def test_resolve_is_keyed_by_name_key_so_casing_collapses(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, _ = pair

    resolved = await repo.resolve(["Urgent", "urgent", "  URGENT  "])

    assert list(resolved) == ["urgent"]
    assert len(set(resolved.values())) == 1


async def test_set_for_task_replaces_rather_than_merges(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    task_id = await _task(session, "t")
    first = await repo.resolve(["a", "b"])
    await repo.set_for_task(task_id, list(first.values()))

    second = await repo.resolve(["c"])
    await repo.set_for_task(task_id, list(second.values()))

    assert (await repo.names_for_tasks([task_id]))[task_id] == ["c"]


async def test_names_for_tasks_is_batch_and_sorted(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    one, two = await _task(session, "one"), await _task(session, "two")
    resolved = await repo.resolve(["zebra", "alpha"])
    await repo.set_for_task(one, list(resolved.values()))
    await repo.set_for_task(two, [resolved["alpha"]])

    names = await repo.names_for_tasks([one, two])

    assert names[one] == ["alpha", "zebra"]
    assert names[two] == ["alpha"]


async def test_names_for_tasks_omits_untagged_and_tolerates_empty_input(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    bare = await _task(session, "bare")

    assert await repo.names_for_tasks([bare]) == {}
    assert await repo.names_for_tasks([]) == {}


async def test_task_ids_matching_all_requires_every_tag(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    both, one = await _task(session, "both"), await _task(session, "one")
    resolved = await repo.resolve(["x", "y"])
    await repo.set_for_task(both, list(resolved.values()))
    await repo.set_for_task(one, [resolved["x"]])

    assert await repo.task_ids_matching(["x", "y"], match_all=True) == {both}


async def test_task_ids_matching_any_accepts_a_single_hit(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    both, one = await _task(session, "both"), await _task(session, "one")
    resolved = await repo.resolve(["x", "y"])
    await repo.set_for_task(both, list(resolved.values()))
    await repo.set_for_task(one, [resolved["x"]])

    assert await repo.task_ids_matching(["x", "y"], match_all=False) == {both, one}


@pytest.mark.parametrize("match_all", [True, False])
async def test_task_ids_matching_is_empty_for_unknown_names(
    pair: tuple[TagRepositoryInterface, AsyncSession], match_all: bool
) -> None:
    repo, _ = pair

    assert await repo.task_ids_matching(["never-used"], match_all=match_all) == set()


async def test_list_with_counts_includes_unused_tags(
    pair: tuple[TagRepositoryInterface, AsyncSession],
) -> None:
    repo, session = pair
    task_id = await _task(session, "t")
    resolved = await repo.resolve(["used", "unused"])
    await repo.set_for_task(task_id, [resolved["used"]])

    counts = {tag.name: count for tag, count in await repo.list_with_counts()}

    assert counts == {"used": 1, "unused": 0}


async def test_get_raises_for_a_missing_tag(pair: tuple[TagRepositoryInterface, AsyncSession]) -> None:
    repo, _ = pair

    with pytest.raises(TagNotFoundError):
        await repo.get(uuid.uuid7())


async def test_task_count_tracks_the_join(pair: tuple[TagRepositoryInterface, AsyncSession]) -> None:
    repo, session = pair
    task_id = await _task(session, "t")
    resolved = await repo.resolve(["counted"])

    assert await repo.task_count(resolved["counted"]) == 0
    await repo.set_for_task(task_id, list(resolved.values()))
    assert await repo.task_count(resolved["counted"]) == 1


async def test_remove_deletes_the_tag(pair: tuple[TagRepositoryInterface, AsyncSession]) -> None:
    repo, session = pair
    resolved = await repo.resolve(["doomed"])
    await session.flush()
    tag: Tag = await repo.get(resolved["doomed"])

    await repo.remove(tag, events=[])

    with pytest.raises(TagNotFoundError):
        await repo.get(resolved["doomed"])
