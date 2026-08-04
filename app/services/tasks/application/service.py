import uuid
from typing import Any

from app.core.event_bus import Event
from app.services.tasks.application.dto import TaskListParams
from app.services.tasks.domain.events import (
    TaskCompleted,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)
from app.services.tasks.domain.models import Task
from app.services.tasks.errors import DuplicateTaskError, EmptyUpdateError
from app.services.tasks.interfaces import TaskRepositoryInterface
from app.services.workflows.domain.engine import TransitionContext, WorkflowEngine
from app.services.workflows.domain.models import Transition
from app.services.workflows.interfaces import WorkflowRepositoryInterface


class TaskService:
    def __init__(
        self,
        *,
        repo: TaskRepositoryInterface,
        workflows: WorkflowRepositoryInterface,
    ) -> None:
        self._repo = repo
        self._workflows = workflows

    async def _engine(self) -> WorkflowEngine:
        """Wrap the active definition, read fresh. Read-only callers (``legal_moves``) use
        this directly; every mutator enters through ``_guarded_engine`` instead."""
        return WorkflowEngine((await self._workflows.get_active()).workflow)

    async def _guarded_engine(self) -> WorkflowEngine:
        """Acquire the workflow advisory guard SHARED (task writes only read the definition,
        so they run concurrently), then read the active definition under it. The single seam
        every status-changing path enters through: the shared lock keeps the read-check-write
        atomic against a concurrent ``PUT /v1/workflow`` (which takes the exclusive lock)
        without serialising task writes against each other."""
        await self._workflows.acquire_workflow_guard(shared=True)
        return await self._engine()

    async def create(
        self,
        *,
        title: str,
        description: str | None,
        status: str | None,
        priority: int,
    ) -> Task:
        engine = await self._guarded_engine()
        # A create enters a state (so it is WIP-checked) but is not a transition, so no role
        # guard can apply — occupancy is the only context a create needs.
        context = await self._context(engine, from_status=None, to_status=status)
        resolved = engine.resolve_entry(status, context=context)
        task = Task.from_input(title=title, description=description, status=resolved, priority=priority)
        await self._persist(task, events=[TaskCreated(task=task.snapshot())], raw_title=title)
        return task

    async def get(self, task_id: uuid.UUID) -> Task:
        return await self._repo.get(task_id)

    async def legal_moves(self, task_id: uuid.UUID) -> tuple[Task, list[Transition]]:
        """The task plus the definition-legal transitions out of its state (read-only — no guard)."""
        engine = await self._engine()
        task = await self._repo.get(task_id)
        return task, engine.legal_moves(task.status)

    async def list(self, *, params: TaskListParams) -> tuple[list[Task], int]:
        return await self._repo.list(
            statuses=params.statuses,
            order_by=params.order_by,
            order_dir=params.order_dir,
            limit=params.limit,
            offset=params.offset,
        )

    async def replace(
        self,
        task_id: uuid.UUID,
        *,
        title: str,
        description: str | None,
        status: str | None,
        priority: int,
        roles: frozenset[str] = frozenset(),
    ) -> Task:
        engine = await self._guarded_engine()
        # Fetching current also gives 404 precedence over any 403/409/422 the checks raise.
        task = await self._repo.get(task_id)
        target = engine.default_entry if status is None else status
        context = await self._context(engine, roles, from_status=task.status, to_status=target)
        engine.check_move(task.status, target, context=context)
        # Snapshot after the checks — a refused write throws the copy away (matches ``patch``).
        previous = task.snapshot()
        task.apply_replace(title=title, description=description, status=target, priority=priority)
        await self._persist_update(task, previous, engine, raw_title=title)
        return task

    async def patch(
        self,
        task_id: uuid.UUID,
        *,
        fields: dict[str, Any],
        # The anonymous actor is the safe default: a role-guarded transition refuses an empty
        # set, so a caller that forgets ``roles`` fails closed rather than bypassing the guard.
        roles: frozenset[str] = frozenset(),
    ) -> Task:
        if not fields:
            raise EmptyUpdateError()
        # A status change consults the workflow, so it takes the guard + reads the definition
        # up front; a non-status patch skips both. ``engine is None`` ⇒ status cannot change.
        engine = await self._guarded_engine() if "status" in fields else None
        task = await self._repo.get(task_id)  # 404 precedence over any 403/409/422 below
        if engine is not None:
            target = fields["status"]
            context = await self._context(engine, roles, from_status=task.status, to_status=target)
            engine.check_move(task.status, target, context=context)
        previous = task.snapshot()
        task.apply_patch(fields)
        # ``fields["title"]`` (raw) if the patch renames; otherwise no collision is possible.
        await self._persist_update(task, previous, engine, raw_title=fields.get("title", task.title))
        return task

    async def delete(self, task_id: uuid.UUID) -> None:
        task = await self._repo.get(task_id)
        snapshot = task.snapshot()
        await self._repo.remove(task, events=[TaskDeleted(task=snapshot)])

    async def _context(
        self,
        engine: WorkflowEngine,
        roles: frozenset[str] = frozenset(),
        *,
        from_status: str | None,
        to_status: str | None,
    ) -> TransitionContext:
        """The guard context for one write: the actor's roles, plus per-status occupancy. The
        occupancy round-trip is issued only when the engine says this write can actually hit a
        ``wip_limit`` — the engine owns that rule, the service only supplies the facts. ``roles``
        defaults to the anonymous actor, which a role-guarded transition refuses."""
        needs = engine.needs_occupancy(from_status=from_status, to_status=to_status)
        return TransitionContext(roles=roles, occupancy=await self._repo.count_by_status() if needs else {})

    async def _persist_update(
        self, updated: Task, previous: Task, engine: WorkflowEngine | None, *, raw_title: str
    ) -> None:
        """Persist a mutated task with its update events — or, if nothing actually changed, do
        nothing (no commit, no events). ``engine`` is None only when status could not change."""
        events = self._update_events(updated, previous, engine)
        if events:
            await self._persist(updated, events=events, raw_title=raw_title)

    async def _persist(self, task: Task, *, events: list[Event], raw_title: str) -> None:
        """Persist through the repo, but re-raise a duplicate with the caller's title verbatim:
        the repo only sees the normalised ``task.title``, and the contract echoes raw input."""
        try:
            await self._repo.persist(task, events=events)
        except DuplicateTaskError as err:
            raise DuplicateTaskError(details={"title": raw_title}, original_error=err.original_error) from err

    def _update_events(self, updated: Task, previous: Task, engine: WorkflowEngine | None) -> list[Event]:
        changed = updated.changed_fields(previous)
        if not changed:
            return []
        snapshot = updated.snapshot()
        events: list[Event] = [TaskUpdated(task=snapshot, previous=previous, changed_fields=changed)]
        if "status" not in changed:
            return events
        assert engine is not None  # status changed ⇒ the caller consulted the definition
        events.append(TaskStatusChanged(task=snapshot, from_status=previous.status, to_status=updated.status))
        if engine.completes(updated.status):
            events.append(TaskCompleted(task=snapshot))
        return events
