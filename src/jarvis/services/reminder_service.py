"""Reminder service -- Milestone 11 Task Group B.

CRUD, status transitions, scheduling *metadata*, and the search hook.

**This service never fires a reminder.** It records when one should
fire and what has happened to it; it starts no loop, registers no
timer, and publishes no ``reminder.fired``. Delivery is M7's Scheduler
(Phase 6), which has not shipped. :meth:`due_before` answers "which
reminders have come due" as a query -- a caller may ask, and nothing
here acts on the answer.

That boundary is the whole reason this service is small. Building a
timer here would be a second scheduler competing with the one the
roadmap already assigns to M7, and this repository's most consistently
enforced rule is that a milestone reuses a system rather than shipping
a parallel copy of it.

Same shape as its Task Group B siblings: ``IDatabase`` per call,
repository inside the session, optional ``EventBus``, a ``search()``
that a source wraps.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.productivity.models import REMINDER_STATUSES, RecurrenceRule
from jarvis.infrastructure.database.repositories import ReminderRepository

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Reminder
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.reminder")


class ReminderService:
    def __init__(
        self,
        *,
        database: IDatabase,
        workspace_service: WorkspaceService | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._workspaces = workspace_service
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    async def create_reminder(
        self,
        workspace_id: str,
        title: str,
        remind_at: datetime,
        *,
        notes: str = "",
        task_id: str | None = None,
        event_id: str | None = None,
        recurrence: RecurrenceRule | None = None,
    ) -> Reminder:
        title = (title or "").strip()
        if not title:
            raise ServiceError("Cannot create a reminder with an empty title.")
        if task_id is not None and event_id is not None:
            # Both would make "what is this reminder about" ambiguous,
            # and the answer would depend on which one a renderer
            # happened to check first.
            raise ServiceError("A reminder may target a task or an event, not both.")
        recurrence = recurrence or RecurrenceRule()
        try:
            recurrence.validate()
        except ValueError as err:
            raise ServiceError(str(err)) from err
        await self._require_workspace(workspace_id)

        async with self._db.session() as sess:
            reminder = await ReminderRepository(sess).add(  # type: ignore[arg-type]
                workspace_id,
                title,
                remind_at,
                notes=notes,
                task_id=task_id,
                event_id=event_id,
                recurrence_json=json.dumps(recurrence.as_dict()),
            )
            reminder_id = reminder.id
        await self._publish(reminder_id, workspace_id, action="created")
        _logger.info("Reminder created: {} ({})", title, reminder_id)
        return await self.require_reminder(reminder_id)

    async def get_reminder(self, reminder_id: str) -> Reminder | None:
        async with self._db.session() as sess:
            return await ReminderRepository(sess).get(reminder_id)  # type: ignore[arg-type]

    async def require_reminder(self, reminder_id: str) -> Reminder:
        reminder = await self.get_reminder(reminder_id)
        if reminder is None:
            raise ServiceError(f"Reminder {reminder_id!r} does not exist.")
        return reminder

    async def list_reminders(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        task_id: str | None = None,
        event_id: str | None = None,
    ) -> list[Reminder]:
        _validate(status, REMINDER_STATUSES, "reminder status")
        async with self._db.session() as sess:
            return await ReminderRepository(sess).list_reminders(  # type: ignore[arg-type]
                workspace_id=workspace_id,
                status=status,
                task_id=task_id,
                event_id=event_id,
            )

    async def update_reminder(
        self,
        reminder_id: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        remind_at: datetime | None = None,
        status: str | None = None,
        recurrence: RecurrenceRule | None = None,
    ) -> Reminder | None:
        _validate(status, REMINDER_STATUSES, "reminder status")
        if recurrence is not None:
            try:
                recurrence.validate()
            except ValueError as err:
                raise ServiceError(str(err)) from err

        async with self._db.session() as sess:
            reminder = await ReminderRepository(sess).update(  # type: ignore[arg-type]
                reminder_id,
                title=title,
                notes=notes,
                remind_at=remind_at,
                status=status,
                recurrence_json=(
                    json.dumps(recurrence.as_dict()) if recurrence is not None else None
                ),
            )
            if reminder is None:
                return None
            workspace_id = reminder.workspace_id
        action = _ACTION_FOR_STATUS.get(status or "", "updated")
        await self._publish(reminder_id, workspace_id, action=action)
        return await self.get_reminder(reminder_id)

    async def dismiss(self, reminder_id: str) -> Reminder | None:
        """The user has seen it and is done with it."""
        return await self.update_reminder(reminder_id, status="dismissed")

    async def cancel(self, reminder_id: str) -> Reminder | None:
        """It should not happen at all -- distinct from ``dismissed``,
        which means it already did its job."""
        return await self.update_reminder(reminder_id, status="cancelled")

    async def delete_reminder(self, reminder_id: str) -> bool:
        async with self._db.session() as sess:
            repo = ReminderRepository(sess)  # type: ignore[arg-type]
            reminder = await repo.get(reminder_id)
            if reminder is None:
                return False
            workspace_id = reminder.workspace_id
            await repo.delete(reminder_id)
        await self._publish(reminder_id, workspace_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Scheduling metadata -- read-only, never a trigger
    # ------------------------------------------------------------------
    async def due_before(
        self, moment: datetime, *, workspace_id: str | None = None
    ) -> list[Reminder]:
        """Pending reminders whose time has arrived.

        A question, not a doorbell. Nothing in this task group calls it
        on a timer; when M7's Scheduler ships, this is the method it
        will poll, and its status transitions are the ones it will
        drive.
        """
        async with self._db.session() as sess:
            return await ReminderRepository(sess).list_due_before(  # type: ignore[arg-type]
                moment, workspace_id=workspace_id
            )

    async def recurrence_of(self, reminder_id: str) -> RecurrenceRule:
        return decode_recurrence((await self.require_reminder(reminder_id)).recurrence_json)

    async def next_occurrence_after(self, reminder_id: str, moment: datetime) -> datetime | None:
        """The next time this reminder would come due after *moment*,
        or ``None`` for a one-shot that has already passed.

        Computed from the stored rule, not from a schedule -- expansion
        is a pure function (see ``domain/productivity/models.py``), and
        answering "when next" without a scheduler is exactly the
        metadata this task group is scoped to provide.

        Returns an **aware** datetime even though SQLite hands the
        stored value back naive: a caller comparing this against
        ``datetime.now(UTC)`` would otherwise hit
        ``TypeError: can't compare offset-naive and offset-aware``, and
        a return value whose tzinfo depends on which backend answered is
        not one anybody can use safely.
        """
        reminder = await self.require_reminder(reminder_id)
        rule = decode_recurrence(reminder.recurrence_json)
        for occurrence in rule.occurrences(reminder.remind_at):
            if _aware(occurrence) > _aware(moment):
                return _aware(occurrence)
        return None

    # ------------------------------------------------------------------
    # Search hook
    # ------------------------------------------------------------------
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await ReminderRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=reminder.id,
                title=reminder.title,
                content=reminder.notes,
                source="reminders",
                # A pending reminder is live; a dismissed or cancelled
                # one is history.
                score=1.0 if reminder.status == "pending" else 0.5,
                uri=f"reminder://{reminder.id}",
                metadata={
                    "status": reminder.status,
                    "remind_at": (reminder.remind_at.isoformat() if reminder.remind_at else None),
                    "workspace_id": reminder.workspace_id,
                    "task_id": reminder.task_id,
                    "event_id": reminder.event_id,
                },
            )
            for reminder in hits
        ]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _require_workspace(self, workspace_id: str) -> None:
        if self._workspaces is not None:
            await self._workspaces.require_workspace(workspace_id)

    async def _publish(self, reminder_id: str, workspace_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import ReminderUpdatedEvent

        await self._event_bus.publish(
            ReminderUpdatedEvent(reminder_id=reminder_id, workspace_id=workspace_id, action=action)
        )


#: Status transitions a subscriber is likely to act on get their own
#: action name; everything else is a generic update.
_ACTION_FOR_STATUS: dict[str, str] = {
    "dismissed": "dismissed",
    "cancelled": "cancelled",
}


def decode_recurrence(raw: str) -> RecurrenceRule:
    try:
        payload: Any = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return RecurrenceRule()
    return RecurrenceRule.from_dict(payload if isinstance(payload, dict) else {})


def _validate(value: str | None, allowed: frozenset[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")


def _aware(moment: datetime) -> datetime:
    from datetime import UTC

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
