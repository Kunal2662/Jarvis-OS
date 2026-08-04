"""Task service -- Milestone 11 Task Group B.

Owns the Task domain: CRUD, status, priority, due dates, tags, the
search hook and event publishing. Shaped like ``WorkspaceService`` and
``IntelligenceService`` before it -- an ``IDatabase`` opened per call,
repository built inside that session, optional ``EventBus``, and a
``search()`` a ``SearchSource`` wraps.

**Workspace-scoped, like every other Task Group B entity.** A task needs
a ``workspace_id`` and may optionally name a ``project_id`` -- the same
shape ``Note`` has, and for the same reason: work jotted down before it
is filed is the normal case. Task Group A built that substrate
precisely so B did not have to invent a container.

**Deliberately not here:** no scheduling, no notification, no
recurrence. A task has a due date, and *something noticing that date* is
M7's Scheduler (Phase 6). Recurring tasks are not modelled at all --
recurrence belongs to the calendar in this design, and a task that
repeats is better expressed as an event with a reminder than as a
second recurrence engine.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.productivity.models import (
    TASK_PRIORITIES,
    TASK_PRIORITY_RANK,
    TASK_STATUSES,
    normalize_tags,
)
from jarvis.infrastructure.database.repositories import TaskRepository

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Task
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.task")

#: Statuses that take a task off the active list. Named once so
#: "is this still open" has one definition.
_CLOSED_STATUSES = frozenset({"done", "cancelled"})


class TaskService:
    def __init__(
        self,
        *,
        database: IDatabase,
        workspace_service: WorkspaceService | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        """*workspace_service* is optional so this service stays
        testable against a database alone, but when wired it is what
        turns "that workspace does not exist" into a clear error instead
        of an IntegrityError from three layers down -- the same check
        ``WorkspaceService.create_project`` makes for the same reason."""
        self._db = database
        self._workspaces = workspace_service
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def create_task(
        self,
        workspace_id: str,
        title: str,
        *,
        description: str = "",
        project_id: str | None = None,
        priority: str = "normal",
        due_at: datetime | None = None,
        tags: list[str] | None = None,
    ) -> Task:
        title = (title or "").strip()
        if not title:
            raise ServiceError("Cannot create a task with an empty title.")
        _validate(priority, frozenset(TASK_PRIORITIES), "task priority")
        await self._require_workspace(workspace_id)

        async with self._db.session() as sess:
            task = await TaskRepository(sess).add(  # type: ignore[arg-type]
                workspace_id,
                title,
                description=description,
                project_id=project_id,
                priority=priority,
                due_at=due_at,
                tags_json=json.dumps(normalize_tags(tags)),
            )
            task_id = task.id
        await self._publish(task_id, workspace_id, project_id or "", action="created")
        _logger.info("Task created: {} ({})", title, task_id)
        return await self.require_task(task_id)

    async def get_task(self, task_id: str) -> Task | None:
        async with self._db.session() as sess:
            return await TaskRepository(sess).get(task_id)  # type: ignore[arg-type]

    async def require_task(self, task_id: str) -> Task:
        task = await self.get_task(task_id)
        if task is None:
            raise ServiceError(f"Task {task_id!r} does not exist.")
        return task

    async def list_tasks(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        tag: str | None = None,
    ) -> list[Task]:
        _validate(status, TASK_STATUSES, "task status")
        _validate(priority, frozenset(TASK_PRIORITIES), "task priority")
        async with self._db.session() as sess:
            tasks = await TaskRepository(sess).list_tasks(  # type: ignore[arg-type]
                workspace_id=workspace_id,
                project_id=project_id,
                status=status,
                priority=priority,
            )
        if tag is None:
            return tasks
        # Filtered in Python rather than SQL: tags are a JSON list, and a
        # LIKE against the serialized text would match "work" inside
        # "homework". A tag table is the fix if this ever needs to scale
        # past a workspace's worth of tasks -- see `Task`'s docstring.
        needle = tag.strip().lower()
        return [task for task in tasks if needle in decode_tags(task.tags_json)]

    async def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_at: datetime | None = None,
        tags: list[str] | None = None,
        project_id: str | None = None,
        clear_project: bool = False,
        clear_due: bool = False,
    ) -> Task | None:
        _validate(status, TASK_STATUSES, "task status")
        _validate(priority, frozenset(TASK_PRIORITIES), "task priority")

        completed_at: datetime | None = None
        if status is not None:
            # `completed_at` is derived from the transition, not stored
            # by the caller: it is the one field where "when did this
            # finish" must agree with `status`, and letting a caller set
            # them independently is how they drift apart.
            completed_at = datetime.now(UTC) if status == "done" else None

        async with self._db.session() as sess:
            task = await TaskRepository(sess).update(  # type: ignore[arg-type]
                task_id,
                title=title,
                description=description,
                status=status,
                priority=priority,
                due_at=due_at,
                tags_json=json.dumps(normalize_tags(tags)) if tags is not None else None,
                project_id=project_id,
                completed_at=completed_at,
                clear_project=clear_project,
                clear_due=clear_due,
            )
            if task is None:
                return None
            workspace_id, current_project = task.workspace_id, task.project_id or ""
        action = "completed" if status == "done" else "updated"
        await self._publish(task_id, workspace_id, current_project, action=action)
        return await self.get_task(task_id)

    async def complete_task(self, task_id: str) -> Task | None:
        """Convenience for the most common transition. Routes through
        :meth:`update_task` rather than duplicating the completed-at
        rule."""
        return await self.update_task(task_id, status="done")

    async def delete_task(self, task_id: str) -> bool:
        async with self._db.session() as sess:
            repo = TaskRepository(sess)  # type: ignore[arg-type]
            task = await repo.get(task_id)
            if task is None:
                return False
            workspace_id, project_id = task.workspace_id, task.project_id or ""
            await repo.delete(task_id)
        await self._publish(task_id, workspace_id, project_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Reads that are not plain CRUD
    # ------------------------------------------------------------------
    async def tags_for(self, task_id: str) -> list[str]:
        return decode_tags((await self.require_task(task_id)).tags_json)

    async def due_before(self, moment: datetime, *, workspace_id: str | None = None) -> list[Task]:
        """Open tasks due at or before *moment*. A query, not a trigger
        -- nothing here acts on the answer."""
        async with self._db.session() as sess:
            return await TaskRepository(sess).list_due_before(  # type: ignore[arg-type]
                moment, workspace_id=workspace_id
            )

    async def status_counts(self, workspace_id: str) -> dict[str, int]:
        """Every status as a key, including the ones with no tasks, so a
        caller rendering a summary does not have to know the vocabulary
        to fill in the zeroes."""
        async with self._db.session() as sess:
            counts = await TaskRepository(sess).counts_by_status(workspace_id)  # type: ignore[arg-type]
        return {status: counts.get(status, 0) for status in sorted(TASK_STATUSES)}

    # ------------------------------------------------------------------
    # Search hook
    # ------------------------------------------------------------------
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await TaskRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]

        results: list[SearchResult] = []
        for task in hits:
            # An open, urgent task is a better answer than a cancelled
            # one. Deterministic weighting, the same posture M10A set
            # for search scoring and M10B repeated for suggestions.
            base = 0.4 if task.status in _CLOSED_STATUSES else 1.0
            score = base * (1.0 + 0.1 * TASK_PRIORITY_RANK.get(task.priority, 1))
            results.append(
                SearchResult(
                    id=task.id,
                    title=task.title,
                    content=task.description,
                    source="tasks",
                    score=score,
                    uri=f"task://{task.id}",
                    metadata={
                        "status": task.status,
                        "priority": task.priority,
                        "workspace_id": task.workspace_id,
                        "project_id": task.project_id,
                        "tags": decode_tags(task.tags_json),
                    },
                )
            )
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _require_workspace(self, workspace_id: str) -> None:
        if self._workspaces is not None:
            await self._workspaces.require_workspace(workspace_id)

    async def _publish(
        self, task_id: str, workspace_id: str, project_id: str, *, action: str
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import TaskUpdatedEvent

        await self._event_bus.publish(
            TaskUpdatedEvent(
                task_id=task_id,
                workspace_id=workspace_id,
                project_id=project_id,
                action=action,
            )
        )


def decode_tags(raw: str) -> list[str]:
    """Malformed JSON yields no tags rather than raising -- tags are read
    on every task load, and one bad write must not make a task
    unreadable (the same posture ``WorkspaceService`` takes for
    settings)."""
    try:
        payload: Any = json.loads(raw or "[]")
    except (TypeError, ValueError):
        return []
    return normalize_tags(payload) if isinstance(payload, list) else []


def _validate(value: str | None, allowed: frozenset[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")
