"""Productivity managers -- Milestone 11 Task Group B.

``TaskManager`` / ``CalendarManager`` / ``ReminderManager``: the
read-side coordinators for the three domains, following
``WorkspaceManager``'s contract exactly -- they **collect and never
compute**, hold no state, persist nothing, and treat every collaborator
except their own service as optional so a partially-wired container
degrades to less context rather than failing.

**Why three managers rather than one, and why any at all.** Each has a
job its service deliberately does not: the service owns one domain and
one database, and the moment it also reaches into Workspace, Knowledge,
Search and Memory it owns four more subsystems' failure modes. What
makes these three separate rather than one class with a mode flag is
that each answers a genuinely different question:

* :class:`TaskManager` -- *what is on my plate*: overdue, due soon, and
  the status breakdown, assembled across a workspace.
* :class:`CalendarManager` -- *what does this window actually look
  like*: stored events expanded through their recurrence rules into
  concrete occurrences, which no single service call produces.
* :class:`ReminderManager` -- *what is waiting*, and what each reminder
  is attached to, resolved across Tasks and Calendar.

They live in one module because they share those conventions and are
read together; splitting three ~60-line coordinators across three files
would be filing for its own sake.

All three are shared with a single, deliberately narrow module-level
helper (:func:`related_items`) rather than a base class -- composition over
inheritance, the rule this repository states in `ARCHITECTURE.md` §1.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.domain.productivity.models import MAX_OCCURRENCES
from jarvis.services.calendar_service import decode_recurrence

if TYPE_CHECKING:
    from jarvis.core.interfaces.search import SearchResult
    from jarvis.services.calendar_service import CalendarService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.reminder_service import ReminderService
    from jarvis.services.search_service import SearchService
    from jarvis.services.task_service import TaskService
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.productivity_managers")

#: How far ahead "due soon" and the default agenda window look. Seven
#: days is the span a week view shows; a caller wanting another window
#: passes one.
DEFAULT_HORIZON_DAYS = 7

#: How many related items an optional subsystem contributes. Small on
#: purpose -- this is a summary a caller acts on, not an export.
_RELATED_TOP_K = 5


class TaskManager:
    """Composes ``TaskService`` with Workspace, Knowledge, Search and
    Memory. Answers "what is on my plate"."""

    def __init__(
        self,
        task_service: TaskService,
        *,
        workspace_service: WorkspaceService | None = None,
        knowledge_service: KnowledgeService | None = None,
        search_service: SearchService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._tasks = task_service
        self._workspaces = workspace_service
        self._knowledge = knowledge_service
        self._search = search_service
        self._memory = memory_service

    async def agenda(
        self,
        workspace_id: str,
        *,
        now: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> dict[str, Any]:
        """Overdue, due-soon and open counts for one workspace.

        *now* is a parameter rather than a clock read so a caller (and a
        test) can ask "what did this look like on Tuesday" -- the same
        injectable-clock shape ``IntelligenceService`` uses for its
        context signals.
        """
        now = now or datetime.now(UTC)
        horizon = now + timedelta(days=max(0, horizon_days))

        overdue = await self._tasks.due_before(now, workspace_id=workspace_id)
        through_horizon = await self._tasks.due_before(horizon, workspace_id=workspace_id)
        overdue_ids = {task.id for task in overdue}
        due_soon = [task for task in through_horizon if task.id not in overdue_ids]

        return {
            "workspace_id": workspace_id,
            "as_of": now.isoformat(),
            "horizon_days": horizon_days,
            "overdue": [_task_row(task) for task in overdue],
            "due_soon": [_task_row(task) for task in due_soon],
            "status_counts": await self._tasks.status_counts(workspace_id),
        }

    async def context(self, task_id: str) -> dict[str, Any]:
        """One task plus what the neighbouring subsystems relate to it.

        Relatedness is the task's own title and description used as a
        query against Knowledge and Memory -- the same deterministic
        approach ``WorkspaceManager.context`` takes, and honest about
        being text matching rather than a learned association. Task
        Group D replaces this method's body without changing its shape.
        """
        task = await self._tasks.require_task(task_id)
        query = f"{task.title} {task.description}".strip()
        workspace: dict[str, Any] | None = None
        if self._workspaces is not None:
            found = await self._workspaces.get_workspace(task.workspace_id)
            if found is not None:
                workspace = {"id": found.id, "name": found.name}

        return {
            "task": _task_row(task),
            "workspace": workspace,
            "related_knowledge": await related_items(self._knowledge, query, kind="knowledge"),
            "related_memories": await related_items(self._memory, query, kind="memory"),
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """Through the shared ``SearchService`` when wired, so results
        are ranked alongside every other source; otherwise this domain
        alone -- narrower, never wrong."""
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._tasks.search(query, top_k=top_k)


class CalendarManager:
    """Composes ``CalendarService`` with Workspace and the recurrence
    expander. Answers "what does this window look like"."""

    def __init__(
        self,
        calendar_service: CalendarService,
        *,
        workspace_service: WorkspaceService | None = None,
        knowledge_service: KnowledgeService | None = None,
        search_service: SearchService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._calendar = calendar_service
        self._workspaces = workspace_service
        self._knowledge = knowledge_service
        self._search = search_service
        self._memory = memory_service

    async def occurrences(
        self,
        *,
        window_start: datetime,
        window_end: datetime,
        workspace_id: str | None = None,
        calendar_id: str | None = None,
        limit_per_event: int = MAX_OCCURRENCES,
    ) -> list[dict[str, Any]]:
        """Concrete occurrences in a window, expanding each stored
        recurrence rule.

        This is the capability no single service call provides, and the
        reason `CalendarManager` exists: the repository can only filter
        on an event's *stored* start, so a weekly standup created in
        January is invisible to a March query until its rule is
        expanded. Expansion happens here, over rows the service already
        returned, using the pure function in the domain layer.

        Not scheduling: this computes which datetimes a rule produces
        and returns them. Nothing fires.
        """
        events = await self._calendar.list_events(
            calendar_id=calendar_id,
            workspace_id=workspace_id,
            starts_before=window_end,
        )

        rows: list[dict[str, Any]] = []
        for event in events:
            rule = decode_recurrence(event.recurrence_json)
            for moment in rule.occurrences(
                event.starts_at, window_end=window_end, limit=limit_per_event
            ):
                if _aware(moment) < _aware(window_start):
                    continue
                rows.append(
                    {
                        "event_id": event.id,
                        "calendar_id": event.calendar_id,
                        "title": event.title,
                        "category": event.category,
                        "location": event.location,
                        "all_day": event.all_day,
                        "starts_at": moment.isoformat(),
                        "is_recurring": rule.is_recurring,
                    }
                )
        rows.sort(key=lambda row: row["starts_at"])
        return rows

    async def agenda(
        self,
        workspace_id: str,
        *,
        now: datetime | None = None,
        horizon_days: int = DEFAULT_HORIZON_DAYS,
    ) -> dict[str, Any]:
        now = now or datetime.now(UTC)
        return {
            "workspace_id": workspace_id,
            "as_of": now.isoformat(),
            "horizon_days": horizon_days,
            "calendars": [
                {"id": c.id, "name": c.name, "is_default": c.is_default}
                for c in await self._calendar.list_calendars(workspace_id=workspace_id)
            ],
            "occurrences": await self.occurrences(
                window_start=now,
                window_end=now + timedelta(days=max(0, horizon_days)),
                workspace_id=workspace_id,
            ),
        }

    async def context(self, event_id: str) -> dict[str, Any]:
        event = await self._calendar.require_event(event_id)
        rule = decode_recurrence(event.recurrence_json)
        query = f"{event.title} {event.description}".strip()
        return {
            "event": {
                "id": event.id,
                "calendar_id": event.calendar_id,
                "title": event.title,
                "description": event.description,
                "category": event.category,
                "location": event.location,
                "starts_at": event.starts_at.isoformat() if event.starts_at else None,
                "ends_at": event.ends_at.isoformat() if event.ends_at else None,
                "all_day": event.all_day,
            },
            "recurrence": rule.as_dict(),
            "related_knowledge": await related_items(self._knowledge, query, kind="knowledge"),
            "related_memories": await related_items(self._memory, query, kind="memory"),
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._calendar.search(query, top_k=top_k)


class ReminderManager:
    """Composes ``ReminderService`` with Tasks and Calendar. Answers
    "what is waiting, and what is it about"."""

    def __init__(
        self,
        reminder_service: ReminderService,
        *,
        task_service: TaskService | None = None,
        calendar_service: CalendarService | None = None,
        workspace_service: WorkspaceService | None = None,
        search_service: SearchService | None = None,
    ) -> None:
        self._reminders = reminder_service
        self._tasks = task_service
        self._calendar = calendar_service
        self._workspaces = workspace_service
        self._search = search_service

    async def due_digest(
        self, *, now: datetime | None = None, workspace_id: str | None = None
    ) -> dict[str, Any]:
        """Which reminders have come due, with their targets resolved.

        **A report, not a delivery.** Building this payload sends
        nothing and changes no status -- every reminder in it is still
        ``pending`` afterwards. When M7's Scheduler ships, this is the
        shape it consumes; until then it is what a UI polls to show a
        badge.
        """
        now = now or datetime.now(UTC)
        due = await self._reminders.due_before(now, workspace_id=workspace_id)
        return {
            "as_of": now.isoformat(),
            "workspace_id": workspace_id,
            "due": [await self._describe(reminder) for reminder in due],
            "delivered": False,
            "detail": "Reporting only — reminder delivery is M7's Scheduler (Phase 6).",
        }

    async def context(self, reminder_id: str) -> dict[str, Any]:
        reminder = await self._reminders.require_reminder(reminder_id)
        described = await self._describe(reminder)
        described["next_occurrence"] = _iso(
            await self._reminders.next_occurrence_after(reminder_id, datetime.now(UTC))
        )
        return described

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)
        return await self._reminders.search(query, top_k=top_k)

    async def _describe(self, reminder: Any) -> dict[str, Any]:
        """Resolves a reminder's target across Tasks and Calendar. A
        missing collaborator (or a deleted target) yields ``None``
        rather than failing the whole digest."""
        target: dict[str, Any] | None = None
        if reminder.task_id and self._tasks is not None:
            task = await self._tasks.get_task(reminder.task_id)
            if task is not None:
                target = {"kind": "task", "id": task.id, "title": task.title}
        elif reminder.event_id and self._calendar is not None:
            event = await self._calendar.get_event(reminder.event_id)
            if event is not None:
                target = {"kind": "event", "id": event.id, "title": event.title}

        return {
            "id": reminder.id,
            "title": reminder.title,
            "notes": reminder.notes,
            "status": reminder.status,
            "remind_at": _iso(reminder.remind_at),
            "workspace_id": reminder.workspace_id,
            "target": target,
        }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
async def related_items(collaborator: Any, query: str, *, kind: str) -> list[dict[str, Any]]:
    """Best-effort lookup against Knowledge or Memory.

    One function rather than a base-class method: the managers need the
    same two lines of defensive plumbing, and sharing it through a
    helper keeps them siblings instead of a hierarchy.

    Public rather than module-private because Task Group C's managers
    need exactly this and importing a underscore-prefixed name across
    modules would be reaching into another module's internals; copying
    it would be worse still.
    """
    if collaborator is None or not query:
        return []
    try:
        if kind == "knowledge":
            hits = await collaborator.search(query, top_k=_RELATED_TOP_K)
            return [{"id": h.id, "title": h.title, "score": h.score} for h in hits]
        records = await collaborator.recall(query, top_k=_RELATED_TOP_K)
        return [
            {"id": getattr(r, "id", ""), "content": getattr(r, "content", "")}
            for r in (records or [])
        ]
    except Exception as err:  # pragma: no cover -- defensive
        _logger.debug("{} lookup for productivity context failed: {}", kind, err)
        return []


def _task_row(task: Any) -> dict[str, Any]:
    from jarvis.services.task_service import decode_tags

    return {
        "id": task.id,
        "title": task.title,
        "status": task.status,
        "priority": task.priority,
        "due_at": _iso(task.due_at),
        "project_id": task.project_id,
        "workspace_id": task.workspace_id,
        "tags": decode_tags(task.tags_json),
    }


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
