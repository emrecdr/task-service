"""Transactional outbox: transactional write, serialization round-trip, delivery, retry /
dead-letter, purge safety, and the live in-process relay loop."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.core import database
from app.core import outbox as outbox_mod
from app.core.config import settings
from app.core.event_bus import Event, EventBus
from app.core.outbox import OutboxRecord, OutboxRelay, deliver_pending, purge_published, stage_events
from app.main import EVENT_REGISTRY
from app.services.tags.domain.events import TAG_EVENT_TYPES
from app.services.tasks.domain.events import TASK_EVENT_TYPES, TaskCreated
from app.services.tasks.domain.models import Task
from app.services.workflows.domain.events import WORKFLOW_EVENT_TYPES, WorkflowUpdated
from httpx import AsyncClient
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

_ALL_EVENT_TYPES = (*TASK_EVENT_TYPES, *TAG_EVENT_TYPES, *WORKFLOW_EVENT_TYPES)


def _task(title: str = "alpha") -> Task:
    return Task.from_input(title=title, description="d", status="in_progress", priority=3)


class _Recorder:
    """A listener that records the events dispatched to it."""

    def __init__(self) -> None:
        self.events: list[Event] = []

    async def __call__(self, event: Event) -> None:
        self.events.append(event)


async def _boom(_event: Event) -> None:
    raise RuntimeError("listener down")


async def _stage(session: AsyncSession, *events: Event) -> None:
    stage_events(session, events)
    await session.commit()


async def _count_rows(session: AsyncSession, *, pending_only: bool = False) -> int:
    stmt = select(func.count()).select_from(OutboxRecord)
    if pending_only:
        stmt = stmt.where(col(OutboxRecord.published_at).is_(None))
    return int(await session.scalar(stmt) or 0)


async def _count_pending(session: AsyncSession) -> int:
    return await _count_rows(session, pending_only=True)


def _delivered(recorder: _Recorder, n: int) -> Callable[[], Awaitable[bool]]:
    async def predicate() -> bool:
        return len(recorder.events) == n

    return predicate


async def _table_empty() -> bool:
    # Its own session: the relay prunes on a different connection than the test's.
    async with database.session_factory() as s:
        return await _count_rows(s) == 0


# --- Serialization / registry ------------------------------------------------


def test_event_registry_covers_every_domain_event() -> None:
    assert set(EVENT_REGISTRY) == {cls.__name__ for cls in _ALL_EVENT_TYPES}


def test_from_event_round_trips_a_nested_task_event() -> None:
    event = TaskCreated(task=_task("round-trip").snapshot())
    row = OutboxRecord.from_event(event)

    assert row.event_type == "TaskCreated"
    assert row.published_at is None
    assert row.retry_count == 0

    rebuilt = EVENT_REGISTRY[row.event_type].model_validate(row.payload)
    assert isinstance(rebuilt, TaskCreated)
    # Event identity coerces back to its declared types — the dedupe key a consumer keys on
    # across at-least-once re-delivery.
    assert rebuilt.id == event.id
    assert rebuilt.occurred_at == event.occurred_at
    # The nested Task's field values round-trip. (A SQLModel ``table=True`` row deserializes its
    # id/created_at as JSON-native strings when nested, so compare values, not typed identity.)
    assert str(rebuilt.task.id) == str(event.task.id)
    assert rebuilt.task.title == "round-trip"
    assert rebuilt.task.status == "in_progress"
    assert rebuilt.task.priority == event.task.priority
    assert rebuilt.task.description == event.task.description


def test_from_event_round_trips_a_scalar_event() -> None:
    event = WorkflowUpdated(version=7, states=["new", "done"])
    rebuilt = EVENT_REGISTRY["WorkflowUpdated"].model_validate(OutboxRecord.from_event(event).payload)
    assert isinstance(rebuilt, WorkflowUpdated)
    assert rebuilt.version == 7
    assert rebuilt.states == ["new", "done"]


# --- Transactional write (end-to-end) ----------------------------------------


async def test_create_writes_one_pending_outbox_row(client: AsyncClient) -> None:
    """A create commits the task row and its event together — one pending outbox row results
    (the relay is disabled under test, so it stays pending)."""
    r = await client.post("/v1/tasks", json={"title": "outbox me", "priority": 2})
    assert r.status_code == 201, r.text

    async with database.session_factory() as session:
        rows = list((await session.scalars(select(OutboxRecord))).all())

    assert len(rows) == 1
    assert rows[0].event_type == "TaskCreated"
    assert rows[0].published_at is None
    assert rows[0].payload["task"]["title"] == "outbox me"


# --- Delivery ----------------------------------------------------------------


async def test_deliver_pending_dispatches_and_marks_published(session: AsyncSession) -> None:
    recorder = _Recorder()
    bus = EventBus()
    bus.subscribe(TaskCreated, recorder)
    await _stage(session, TaskCreated(task=_task().snapshot()))

    delivered = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=5)

    assert delivered == 1
    assert [type(e) for e in recorder.events] == [TaskCreated]
    assert await _count_pending(session) == 0


async def test_deliver_pending_records_failure_and_leaves_pending(session: AsyncSession) -> None:
    bus = EventBus()
    bus.subscribe(TaskCreated, _boom)
    await _stage(session, TaskCreated(task=_task().snapshot()))

    delivered = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=5)

    assert delivered == 1  # claimed, but not published
    row = (await session.scalars(select(OutboxRecord))).one()
    assert row.published_at is None
    assert row.retry_count == 1
    assert row.last_error is not None and "listener down" in row.last_error


class _RecordingLogger:
    """Replaces the module's ``logger`` for tests — records the level and fields of each call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def debug(self, event: str, **fields: Any) -> None:
        self.calls.append(("debug", event, fields))

    def warning(self, event: str, **fields: Any) -> None:
        self.calls.append(("warning", event, fields))

    def error(self, event: str, **fields: Any) -> None:
        self.calls.append(("error", event, fields))


async def test_delivery_failure_logs_only_the_two_alertable_ends(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First failure and death are alertable; the retries between them are not.

    At the default ceiling that middle band is ~300 attempts per row, so emitting them at
    warning would bury the two lines that matter under 100 lines/second at a full batch.
    """
    recorder = _RecordingLogger()
    monkeypatch.setattr(outbox_mod, "logger", recorder)
    bus = EventBus()
    bus.subscribe(TaskCreated, _boom)
    await _stage(session, TaskCreated(task=_task().snapshot()))

    for _ in range(4):  # 4 attempts against a ceiling of 4
        await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=4)

    assert [(level, event) for level, event, _ in recorder.calls] == [
        ("warning", "outbox_delivery_failed"),  # it started failing
        ("debug", "outbox_delivery_failed"),
        ("debug", "outbox_delivery_failed"),
        ("error", "outbox_dead_lettered"),  # it died
    ]
    assert recorder.calls[-1][2]["retry_count"] == 4


async def test_deliver_pending_skips_dead_lettered_rows(session: AsyncSession) -> None:
    # A stamped row is a dead-letter: never claimed again, always retained.
    row = OutboxRecord.from_event(TaskCreated(task=_task().snapshot()))
    row.dead_lettered_at = datetime.now(UTC)
    row.retry_count = 5
    session.add(row)
    await session.commit()

    recorder = _Recorder()
    bus = EventBus()
    bus.subscribe(TaskCreated, recorder)

    delivered = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=5)

    assert delivered == 0
    assert recorder.events == []
    assert await _count_pending(session) == 1


async def test_dead_lettering_is_terminal_not_inferred_from_retry_count(session: AsyncSession) -> None:
    """A raised ceiling must not silently resurrect a dead-letter — the stamp is what counts."""
    bus = EventBus()
    bus.subscribe(TaskCreated, _boom)
    await _stage(session, TaskCreated(task=_task().snapshot()))

    await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=1)
    row = (await session.scalars(select(OutboxRecord))).one()
    assert row.dead_lettered_at is not None

    # Re-poll with a far higher ceiling: under the old retry_count < max_retries predicate this
    # row would be claimed again; the terminal stamp keeps it out.
    claimed = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=99)
    assert claimed == 0
    assert row.retry_count == 1  # untouched — never re-attempted


async def test_re_driving_a_dead_letter_makes_it_deliverable_again(session: AsyncSession) -> None:
    """The operator escape hatch: clear the stamp and the row re-enters the poll."""
    recorder = _Recorder()
    bus = EventBus()
    bus.subscribe(TaskCreated, _boom)
    await _stage(session, TaskCreated(task=_task().snapshot()))
    await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=1)

    row = (await session.scalars(select(OutboxRecord))).one()
    row.dead_lettered_at = None
    row.retry_count = 0
    await session.commit()

    bus = EventBus()  # a healthy listener this time
    bus.subscribe(TaskCreated, recorder)
    delivered = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=10, max_retries=1)

    assert delivered == 1
    assert [type(e) for e in recorder.events] == [TaskCreated]
    assert await _count_pending(session) == 0


async def test_deliver_pending_honours_batch_size(session: AsyncSession) -> None:
    recorder = _Recorder()
    bus = EventBus()
    bus.subscribe(TaskCreated, recorder)
    await _stage(
        session,
        TaskCreated(task=_task("a").snapshot()),
        TaskCreated(task=_task("b").snapshot()),
        TaskCreated(task=_task("c").snapshot()),
    )

    first = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=2, max_retries=5)
    assert first == 2
    assert await _count_pending(session) == 1

    second = await deliver_pending(session, registry=EVENT_REGISTRY, bus=bus, batch_size=2, max_retries=5)
    assert second == 1
    assert await _count_pending(session) == 0


# --- Purge -------------------------------------------------------------------


async def test_purge_published_deletes_only_old_delivered_rows(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    old_delivered = OutboxRecord.from_event(TaskCreated(task=_task("old").snapshot()))
    old_delivered.published_at = now - timedelta(days=8)
    recent_delivered = OutboxRecord.from_event(TaskCreated(task=_task("recent").snapshot()))
    recent_delivered.published_at = now - timedelta(days=1)
    # An ancient but still-*pending* row (delivery has been failing): must NEVER be pruned,
    # even though it is far older than the retention window — this is the whole safety point.
    stuck_pending = OutboxRecord.from_event(TaskCreated(task=_task("stuck").snapshot()))
    stuck_pending.occurred_at = now - timedelta(days=30)
    # A dead-letter is undeliverable *and* ancient, but it is the triage record — pruning it
    # would discard the only evidence the event existed.
    dead = OutboxRecord.from_event(TaskCreated(task=_task("dead").snapshot()))
    dead.occurred_at = now - timedelta(days=90)
    dead.dead_lettered_at = now - timedelta(days=89)
    session.add_all([old_delivered, recent_delivered, stuck_pending, dead])
    await session.commit()

    deleted = await purge_published(session, retention_days=7)

    assert deleted == 1
    remaining = {r.payload["task"]["title"] for r in (await session.scalars(select(OutboxRecord))).all()}
    assert remaining == {"recent", "stuck", "dead"}


async def test_purge_never_deletes_a_dead_letter_even_if_it_was_also_published(
    session: AsyncSession,
) -> None:
    """Dead-letters are the triage record; the prune must exclude them on their own merit.

    No current path sets both stamps — a row publishes or it dead-letters. This pins the
    exclusion to ``dead_lettered_at`` rather than to that fact, so a future change that
    stamps both (say, marking a poisoned row delivered to drain it) cannot silently start
    deleting the evidence.
    """
    both = OutboxRecord.from_event(TaskCreated(task=_task("both").snapshot()))
    both.published_at = datetime.now(UTC) - timedelta(days=30)
    both.dead_lettered_at = datetime.now(UTC) - timedelta(days=30)
    session.add(both)
    await session.commit()

    assert await purge_published(session, retention_days=7) == 0
    assert await _count_rows(session) == 1


async def test_purge_stops_at_the_batch_cap_and_resumes_next_pass(session: AsyncSession) -> None:
    """A pass is bounded so a backlog cannot stall delivery — the relay runs the prune on its
    own task. The remainder is not lost; the next pass picks it up."""
    stale = datetime.now(UTC) - timedelta(days=30)
    for i in range(5):
        row = OutboxRecord.from_event(TaskCreated(task=_task(f"old-{i}").snapshot()))
        row.published_at = stale
        session.add(row)
    await session.commit()

    first = await purge_published(session, retention_days=7, batch_size=2, max_batches=2)
    assert first == 4  # capped mid-backlog
    assert await _count_rows(session) == 1

    second = await purge_published(session, retention_days=7, batch_size=2, max_batches=2)
    assert second == 1  # the rest, on the following pass
    assert await _count_rows(session) == 0


async def test_purge_published_deletes_across_batches(session: AsyncSession) -> None:
    """More rows than one batch: the loop must keep going until the backlog is drained.

    Bounded batches are what keep each DELETE short enough to stay under the statement
    timeout, so "drains fully" is the property that makes the bound safe to add.
    """
    stale = datetime.now(UTC) - timedelta(days=30)
    for i in range(5):
        row = OutboxRecord.from_event(TaskCreated(task=_task(f"old-{i}").snapshot()))
        row.published_at = stale
        session.add(row)
    await session.commit()

    deleted = await purge_published(session, retention_days=7, batch_size=2)  # 2 + 2 + 1

    assert deleted == 5
    assert await _count_rows(session) == 0


# --- The live relay loop -----------------------------------------------------


async def _wait_until(predicate: Callable[[], Awaitable[bool]], *, timeout: float = 5.0) -> None:
    """Poll ``predicate`` until it is true. The relay runs as a background task, so every
    assertion about its effects has to wait for a loop iteration rather than assume one."""
    async with asyncio.timeout(timeout):
        while not await predicate():
            await asyncio.sleep(0.02)


async def test_relay_delivers_pending_rows_then_stops(session: AsyncSession) -> None:
    recorder = _Recorder()
    bus = EventBus()
    bus.subscribe(TaskCreated, recorder)
    await _stage(session, TaskCreated(task=_task("via-relay").snapshot()))

    relay = OutboxRelay(
        bus=bus,
        registry=EVENT_REGISTRY,
        poll_interval=0.05,
        batch_size=10,
        max_retries=5,
        retention_days=7,
        cleanup_interval=3600,
    )
    relay.start()
    try:
        await _wait_until(_delivered(recorder, 1))
    finally:
        await relay.stop()

    assert isinstance(recorder.events[0], TaskCreated)
    async with database.session_factory() as verify:
        row = (await verify.scalars(select(OutboxRecord))).one()
    assert row.published_at is not None


async def test_relay_prunes_old_delivered_rows(session: AsyncSession) -> None:
    # A delivered row past the retention window must be pruned by the relay's cleanup pass.
    old = OutboxRecord.from_event(TaskCreated(task=_task("ancient").snapshot()))
    old.published_at = datetime.now(UTC) - timedelta(days=10)
    session.add(old)
    await session.commit()

    relay = OutboxRelay(
        bus=EventBus(),
        registry=EVENT_REGISTRY,
        poll_interval=0.05,
        batch_size=10,
        max_retries=5,
        retention_days=7,
        cleanup_interval=0.01,  # prune on the first loop
    )
    relay.start()
    try:
        await _wait_until(_table_empty)
    finally:
        await relay.stop()


def test_relay_from_settings_constructs_with_configured_values() -> None:
    relay = OutboxRelay.from_settings(bus=EventBus(), registry=EVENT_REGISTRY)
    # Every setting must reach its matching constructor parameter — an isinstance check alone
    # passes even when ``from_settings`` swaps two of them (e.g. poll for cleanup interval).
    assert relay._poll_interval == settings.outbox_poll_interval_seconds  # pyright: ignore[reportPrivateUsage]
    assert relay._batch_size == settings.outbox_batch_size  # pyright: ignore[reportPrivateUsage]
    assert relay._max_retries == settings.outbox_max_retries  # pyright: ignore[reportPrivateUsage]
    assert relay._retention_days == settings.outbox_retention_days  # pyright: ignore[reportPrivateUsage]
    assert relay._cleanup_interval == settings.outbox_cleanup_interval_seconds  # pyright: ignore[reportPrivateUsage]
