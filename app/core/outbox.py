"""Transactional outbox — durable, at-least-once delivery of domain events.

Each write stages its events into the ``outbox`` table **inside the same transaction** as
the row change (see the feature repositories), so a task and its events commit or roll back
together — no event is ever lost to a crash between commit and fan-out. A single in-process
relay (``OutboxRelay``, started in the app lifespan) then claims pending rows with
``FOR UPDATE SKIP LOCKED`` (multi-worker-safe), reconstructs each event from its stored
payload, dispatches it to the registered listeners, and marks the row published. Delivery is
**at-least-once**: a crash after dispatch but before the mark re-delivers on the next poll, so
listeners must be idempotent (they key off ``event.id``, which round-trips in the payload).

Failure is self-healing: a row that fails delivery keeps ``published_at IS NULL`` and its
``retry_count`` climbs, so the next poll retries it. Retries carry no backoff, so
``max_retries × poll_interval`` is the outage a delivery survives (defaults ≈ 5 minutes);
past that the row is **dead-lettered** — stamped ``dead_lettered_at``, dropped from the poll's
partial index, and kept for triage (never auto-pruned). Dead-lettering is terminal by design:
re-driving one is a deliberate operator action (clear ``dead_lettered_at`` and ``retry_count``),
not something a change to ``max_retries`` does silently. Only *delivered* rows age out, via
``purge_published``, so the table stays bounded while the deliverable-rows index keeps the poll
fast regardless of history.

**Listener latency budget.** A batch is claimed with row locks held until the poll's single
commit, so the claiming transaction stays open for as long as the listeners take. Handlers
must therefore be fast and non-blocking: work that can stall (network calls, third-party
APIs) belongs behind its own queue, enqueued by the listener rather than performed inside it.
A slow handler does not lose events, but it holds locks and delays sibling workers re-claiming
the batch.
"""

import asyncio
import contextlib
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Self, cast

from sqlalchemy import Column, CursorResult, DateTime, Index, delete, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import Field, SQLModel, col, select

from app.core.config import settings
from app.core.constants import OUTBOX_LAST_ERROR_MAX_LENGTH, OUTBOX_PURGE_BATCH_SIZE
from app.core.database import session_factory
from app.core.event_bus import Event, EventBus
from app.core.logging import logger

# Registry mapping an event's stored ``event_type`` (its class name) back to the class, so the
# relay can rebuild the typed ``Event`` a listener expects. Built at wiring time (app.main),
# where both features are already imported — keeping this module free of any service import.
type EventRegistry = Mapping[str, type[Event]]


class OutboxRecord(SQLModel, table=True):
    """One durable event awaiting delivery. ``published_at IS NULL`` ⇒ pending."""

    __tablename__ = "outbox"  # pyright: ignore[reportAssignmentType]
    __table_args__ = (
        # Partial index over the poll's exact predicate + order key, so the "find the next
        # batch" scan stays small no matter how much history accumulates. Dead-letters are
        # excluded by predicate rather than by a ``retry_count`` filter: they are permanently
        # undeliverable and, being the oldest rows, would otherwise sort *first* and be
        # re-examined on every tick forever. (``retry_count < N`` could not live here anyway —
        # an index predicate must be immutable, so it cannot reference a runtime setting.)
        Index(
            "ix_outbox_deliverable",
            "occurred_at",
            postgresql_where=text("published_at IS NULL AND dead_lettered_at IS NULL"),
        ),
        # Drives the retention prune. Fresh rows have ``published_at IS NULL`` so they never
        # enter this index — it costs the request-path insert nothing, and gains an entry only
        # when the relay marks a row delivered, off the hot path.
        Index(
            "ix_outbox_published_at",
            "published_at",
            postgresql_where=text("published_at IS NOT NULL"),
        ),
    )

    # Storage id (uuid7, time-ordered) — distinct from the *event's* id, which lives in the
    # payload and is what consumers dedupe on across at-least-once re-delivery.
    id: uuid.UUID = Field(default_factory=uuid.uuid7, primary_key=True)
    event_type: str
    payload: dict[str, Any] = Field(sa_column=Column(JSONB, nullable=False))
    occurred_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))  # timestamptz
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    # Terminal marker: set once delivery has failed ``max_retries`` times. Explicit rather than
    # inferred from ``retry_count`` so the state survives a change to that setting — re-driving
    # a dead-letter is a deliberate operator action (clear this and ``retry_count``), not the
    # side effect of an edit to config.
    dead_lettered_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    retry_count: int = Field(default=0)
    last_error: str | None = Field(default=None)

    @classmethod
    def from_event(cls, event: Event) -> Self:
        """Serialize a domain event into a pending row. ``mode="json"`` yields JSONB-safe
        primitives (uuid/datetime → strings) that ``model_validate`` reverses on delivery."""
        return cls(
            event_type=type(event).__name__,
            payload=event.model_dump(mode="json"),
            occurred_at=event.occurred_at,
        )


def stage_events(session: AsyncSession, events: Sequence[Event]) -> None:
    """Add ``events`` as pending outbox rows on ``session`` — the one place a domain event
    becomes a row. Callers stage this alongside their row change so a single commit persists
    both (the transactional-outbox atomicity guarantee)."""
    for event in events:
        session.add(OutboxRecord.from_event(event))


async def deliver_pending(
    session: AsyncSession,
    *,
    registry: EventRegistry,
    bus: EventBus,
    batch_size: int,
    max_retries: int,
) -> int:
    """Claim one batch of pending rows, deliver each, and commit the outcomes. Returns the
    number of rows claimed (``< batch_size`` ⇒ the queue is drained for now).

    ``FOR UPDATE SKIP LOCKED`` lets concurrent relays (one per worker) claim disjoint rows
    without blocking each other. A delivery failure is isolated to its own row — it is retried
    on a later poll, not lost, and never poisons the rest of the batch.
    """
    stmt = (
        select(OutboxRecord)
        .where(col(OutboxRecord.published_at).is_(None), col(OutboxRecord.dead_lettered_at).is_(None))
        .order_by(col(OutboxRecord.occurred_at).asc(), col(OutboxRecord.id).asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    rows = list((await session.scalars(stmt)).all())
    for row in rows:
        try:
            # Rebuilds the typed event; its identity (id/occurred_at) coerces back, while a
            # nested SQLModel-row payload deserializes as JSON-native values (immaterial to the
            # log-only listeners — a consumer needing typed row fields would re-validate).
            event = registry[row.event_type].model_validate(row.payload)
            await bus.dispatch(event)
        except Exception as err:  # noqa: BLE001 - any listener/reconstruction error is a retryable delivery failure
            reason = str(err)
            row.retry_count += 1
            row.last_error = reason[:OUTBOX_LAST_ERROR_MAX_LENGTH]
            dead_lettered = row.retry_count >= max_retries
            if dead_lettered:
                row.dead_lettered_at = datetime.now(UTC)
            # Only the two ends of a failure are alertable: it started failing, and it died.
            # The retries between them say nothing new, and at ``max_retries`` 300 they would
            # be 300 lines per row (100/s at a full batch) — so they drop to debug.
            emit = logger.error if dead_lettered else (logger.warning if row.retry_count == 1 else logger.debug)
            emit(
                "outbox_dead_lettered" if dead_lettered else "outbox_delivery_failed",
                outbox_id=str(row.id),
                event_type=row.event_type,
                retry_count=row.retry_count,
                error=reason,
            )
        else:
            row.published_at = datetime.now(UTC)
    await session.commit()
    return len(rows)


async def purge_published(session: AsyncSession, *, retention_days: int) -> int:
    """Delete delivered rows at least ``retention_days`` old; returns the count removed.

    Filters on ``published_at`` (the delivered stamp), never ``occurred_at`` — an old row
    that is still pending means delivery has been failing, exactly what must NOT be dropped.

    Deletes in bounded batches, each its own transaction. One unbounded DELETE over a whole
    retention window holds its locks and accumulates its WAL for as long as it runs, which on
    a large table means exceeding ``db_statement_timeout_ms`` and failing outright; short
    statements also let autovacuum reclaim the dead tuples as they are produced.
    """
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    due = (
        select(col(OutboxRecord.id))
        .where(col(OutboxRecord.published_at).is_not(None), col(OutboxRecord.published_at) <= cutoff)
        .limit(OUTBOX_PURGE_BATCH_SIZE)
    )
    deleted = 0
    while True:
        batch = list((await session.scalars(due)).all())
        if not batch:
            return deleted
        # ``execute`` is typed as ``Result``; a DELETE returns a ``CursorResult`` with ``rowcount``.
        result = cast(
            "CursorResult[Any]", await session.execute(delete(OutboxRecord).where(col(OutboxRecord.id).in_(batch)))
        )
        await session.commit()
        deleted += result.rowcount or 0
        if len(batch) < OUTBOX_PURGE_BATCH_SIZE:
            return deleted


class OutboxRelay:
    """Owns the in-process poll loop: deliver pending events, and periodically prune delivered
    rows. One instance per worker, started/stopped by the app lifespan."""

    def __init__(
        self,
        *,
        bus: EventBus,
        registry: EventRegistry,
        poll_interval: float,
        batch_size: int,
        max_retries: int,
        retention_days: int,
        cleanup_interval: float,
    ) -> None:
        self._bus = bus
        self._registry = registry
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._retention_days = retention_days
        self._cleanup_interval = cleanup_interval
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @classmethod
    def from_settings(cls, *, bus: EventBus, registry: EventRegistry) -> Self:
        return cls(
            bus=bus,
            registry=registry,
            poll_interval=settings.outbox_poll_interval_seconds,
            batch_size=settings.outbox_batch_size,
            max_retries=settings.outbox_max_retries,
            retention_days=settings.outbox_retention_days,
            cleanup_interval=settings.outbox_cleanup_interval_seconds,
        )

    def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="outbox-relay")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task
            self._task = None

    async def _run(self) -> None:
        # ``monotonic`` clock for scheduling — immune to wall-clock jumps.
        next_cleanup = time.monotonic() + self._cleanup_interval
        while not self._stop.is_set():
            processed = await self._tick()
            if time.monotonic() >= next_cleanup:
                await self._cleanup()
                next_cleanup = time.monotonic() + self._cleanup_interval
            # A full batch likely means more waiting — loop straight back; otherwise idle.
            if processed < self._batch_size:
                await self._sleep(self._poll_interval)

    async def _tick(self) -> int:
        try:
            async with session_factory() as session:
                return await deliver_pending(
                    session,
                    registry=self._registry,
                    bus=self._bus,
                    batch_size=self._batch_size,
                    max_retries=self._max_retries,
                )
        except Exception:  # noqa: BLE001 - the loop must survive a transient DB error and retry next tick
            logger.exception("outbox_relay_tick_failed")
            return 0

    async def _cleanup(self) -> None:
        try:
            async with session_factory() as session:
                deleted = await purge_published(session, retention_days=self._retention_days)
            if deleted:
                logger.info("outbox_pruned", deleted=deleted)
        except Exception:  # noqa: BLE001 - pruning is best-effort; a failure must not kill the relay
            logger.exception("outbox_relay_cleanup_failed")

    async def _sleep(self, seconds: float) -> None:
        # Sleep, but wake immediately on shutdown so ``stop()`` is responsive.
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
