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
