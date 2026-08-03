"""The advisory guard restores atomicity the single SQLite connection gave for free.

Under async Postgres + a real connection pool, ``replace_active``'s max(version) → insert
→ commit span is no longer serialised by a single connection. The ``pg_advisory_xact_lock``
in ``acquire_workflow_guard`` serialises it again. This proves it: N concurrent workflow
writes, each on its own session/connection, must produce N distinct sequential versions —
without the lock, two would read the same max(version) and collide on the unique constraint.
"""

import asyncio

from app.core import database
from app.core.event_bus import EventBus
from app.services.workflows.application.service import WorkflowService
from app.services.workflows.infrastructure.repository import SQLModelWorkflowRepository
from app.services.workflows.interfaces import StatusUsagePort
from fastapi import BackgroundTasks

_DOC = {
    "states": [{"name": "open", "initial": True}, "closed"],
    "transitions": [{"name": "Close", "from": "open", "to": "closed"}],
}


class _NoUsage(StatusUsagePort):
    async def count_by_status(self) -> dict[str, int]:
        return {}


async def test_concurrent_workflow_writes_get_distinct_versions() -> None:
    n = 8
    sessions = [database.get_sessionmaker()() for _ in range(n)]
    services = [
        WorkflowService(repo=SQLModelWorkflowRepository(s), usage=_NoUsage(), events=EventBus()) for s in sessions
    ]
    bt = BackgroundTasks()

    async def put(svc: WorkflowService) -> int:
        stored = await svc.replace_active(document=_DOC, background_tasks=bt)
        return stored.version

    try:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(put(svc)) for svc in services]
    finally:
        for s in sessions:
            await s.close()

    versions = sorted(t.result() for t in tasks)
    # Seed is version 1; the N concurrent writes serialise into 2..N+1, all distinct.
    assert versions == list(range(2, 2 + n))


async def test_shared_guards_do_not_block_each_other() -> None:
    # Task-status writes take the SHARED guard; multiple must be held at once. Were this the
    # exclusive lock, the second acquire would block until the first's txn ends (→ time out).
    s1 = database.get_sessionmaker()()
    s2 = database.get_sessionmaker()()
    try:
        await asyncio.wait_for(SQLModelWorkflowRepository(s1).acquire_workflow_guard(shared=True), timeout=5)
        await asyncio.wait_for(SQLModelWorkflowRepository(s2).acquire_workflow_guard(shared=True), timeout=5)
    finally:
        await s1.rollback()
        await s2.rollback()
        await s1.close()
        await s2.close()


async def test_exclusive_guard_waits_for_a_shared_holder() -> None:
    # The anti-stranding invariant: a workflow PUT (EXCLUSIVE) must not proceed while a task
    # write (SHARED) is in flight. Hold shared, assert exclusive blocks, release, assert it runs.
    s_shared = database.get_sessionmaker()()
    s_excl = database.get_sessionmaker()()
    excl_task: asyncio.Task[None] | None = None
    try:
        await SQLModelWorkflowRepository(s_shared).acquire_workflow_guard(shared=True)
        excl_task = asyncio.create_task(SQLModelWorkflowRepository(s_excl).acquire_workflow_guard(shared=False))
        await asyncio.sleep(0.5)
        assert not excl_task.done(), "exclusive guard must block while a shared guard is held"
        await s_shared.rollback()  # release the shared holder
        await asyncio.wait_for(excl_task, timeout=5)  # exclusive now proceeds
        assert excl_task.done() and excl_task.exception() is None
    finally:
        if excl_task is not None and not excl_task.done():
            excl_task.cancel()
        await s_shared.rollback()
        await s_excl.rollback()
        await s_shared.close()
        await s_excl.close()
