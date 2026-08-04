"""Calendar service -- Milestone 11 Task Group B.

The **local** calendar engine: calendars, events, categories, metadata,
recurrence rules and the search hook. No external provider, no
synchronization -- Google, Outlook and friends are Task Group E, and
this deliberately builds the local model they will later map onto
rather than a client for any of them.

Same shape as ``WorkspaceService``/``TaskService``: ``IDatabase`` per
call, repository inside the session, optional ``EventBus``, a
``search()`` a source wraps.

**Recurrence is stored, never materialized.** An event keeps its rule;
occurrences are computed on demand by ``RecurrenceRule.occurrences``.
Writing 100 rows for a yearly event would mean editing the series has to
find and rewrite all of them, and a rule the user can still read back is
worth more than a table of dates they cannot.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.productivity.models import EVENT_CATEGORIES, RecurrenceRule
from jarvis.infrastructure.database.repositories import CalendarRepository

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Calendar, CalendarEvent
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.calendar")

#: Name given to the calendar created automatically for a workspace that
#: has none. A caller adding an event should not have to create a
#: container first.
DEFAULT_CALENDAR_NAME = "General"


class CalendarService:
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
    # Calendars
    # ------------------------------------------------------------------
    async def create_calendar(
        self,
        workspace_id: str,
        name: str,
        *,
        description: str = "",
        color: str = "",
        is_default: bool = False,
    ) -> Calendar:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a calendar with an empty name.")
        await self._require_workspace(workspace_id)

        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            calendar = await repo.add_calendar(
                workspace_id,
                name,
                description=description,
                color=color,
                is_default=is_default,
            )
            calendar_id = calendar.id
            if is_default:
                await repo.clear_default(workspace_id, except_id=calendar_id)
        await self._publish_calendar(calendar_id, workspace_id, action="created")
        return await self.require_calendar(calendar_id)

    async def get_calendar(self, calendar_id: str) -> Calendar | None:
        async with self._db.session() as sess:
            return await CalendarRepository(sess).get_calendar(calendar_id)  # type: ignore[arg-type]

    async def require_calendar(self, calendar_id: str) -> Calendar:
        calendar = await self.get_calendar(calendar_id)
        if calendar is None:
            raise ServiceError(f"Calendar {calendar_id!r} does not exist.")
        return calendar

    async def list_calendars(self, *, workspace_id: str | None = None) -> list[Calendar]:
        async with self._db.session() as sess:
            return await CalendarRepository(sess).list_calendars(  # type: ignore[arg-type]
                workspace_id=workspace_id
            )

    async def ensure_default_calendar(self, workspace_id: str) -> Calendar:
        """The workspace's default calendar, created on first use.

        Lazily rather than as a side effect of creating a workspace:
        Task Group A's ``WorkspaceService`` should not have to know this
        task group exists, and a workspace nobody schedules anything in
        does not need a calendar row.
        """
        async with self._db.session() as sess:
            existing = await CalendarRepository(sess).default_calendar(  # type: ignore[arg-type]
                workspace_id
            )
            if existing is not None:
                return existing
        return await self.create_calendar(workspace_id, DEFAULT_CALENDAR_NAME, is_default=True)

    async def update_calendar(
        self,
        calendar_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        is_default: bool | None = None,
    ) -> Calendar | None:
        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            calendar = await repo.update_calendar(
                calendar_id,
                name=name,
                description=description,
                color=color,
                is_default=is_default,
            )
            if calendar is None:
                return None
            workspace_id = calendar.workspace_id
            if is_default:
                await repo.clear_default(workspace_id, except_id=calendar_id)
        await self._publish_calendar(calendar_id, workspace_id, action="updated")
        return await self.get_calendar(calendar_id)

    async def delete_calendar(self, calendar_id: str) -> bool:
        """Deletes the calendar **and its events** -- unlike deleting a
        project, which keeps its notes.

        The asymmetry is deliberate. A note outlives the project it was
        filed under because it is content in its own right; an event
        without a calendar is not "unfiled", it is meaningless -- there
        is no workspace-level event list for it to fall back to.
        """
        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            calendar = await repo.get_calendar(calendar_id)
            if calendar is None:
                return False
            workspace_id = calendar.workspace_id
            await repo.delete_calendar(calendar_id)
        await self._publish_calendar(calendar_id, workspace_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def create_event(
        self,
        calendar_id: str,
        title: str,
        starts_at: datetime,
        *,
        description: str = "",
        location: str = "",
        category: str = "general",
        ends_at: datetime | None = None,
        all_day: bool = False,
        recurrence: RecurrenceRule | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CalendarEvent:
        title = (title or "").strip()
        if not title:
            raise ServiceError("Cannot create an event with an empty title.")
        _validate(category, EVENT_CATEGORIES, "event category")
        if ends_at is not None and ends_at < starts_at:
            raise ServiceError("An event cannot end before it starts.")
        recurrence = recurrence or RecurrenceRule()
        try:
            recurrence.validate()
        except ValueError as err:
            raise ServiceError(str(err)) from err
        calendar = await self.require_calendar(calendar_id)

        async with self._db.session() as sess:
            event = await CalendarRepository(sess).add_event(  # type: ignore[arg-type]
                calendar_id,
                title,
                starts_at,
                description=description,
                location=location,
                category=category,
                ends_at=ends_at,
                all_day=all_day,
                recurrence_json=json.dumps(recurrence.as_dict()),
                meta_json=json.dumps(metadata or {}),
            )
            event_id = event.id
        await self._publish_event(event_id, calendar_id, calendar.workspace_id, action="created")
        return await self.require_event(event_id)

    async def get_event(self, event_id: str) -> CalendarEvent | None:
        async with self._db.session() as sess:
            return await CalendarRepository(sess).get_event(event_id)  # type: ignore[arg-type]

    async def require_event(self, event_id: str) -> CalendarEvent:
        event = await self.get_event(event_id)
        if event is None:
            raise ServiceError(f"Event {event_id!r} does not exist.")
        return event

    async def list_events(
        self,
        *,
        calendar_id: str | None = None,
        workspace_id: str | None = None,
        category: str | None = None,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
    ) -> list[CalendarEvent]:
        _validate(category, EVENT_CATEGORIES, "event category")
        async with self._db.session() as sess:
            return await CalendarRepository(sess).list_events(  # type: ignore[arg-type]
                calendar_id=calendar_id,
                workspace_id=workspace_id,
                category=category,
                starts_after=starts_after,
                starts_before=starts_before,
            )

    async def update_event(
        self,
        event_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        location: str | None = None,
        category: str | None = None,
        starts_at: datetime | None = None,
        ends_at: datetime | None = None,
        all_day: bool | None = None,
        recurrence: RecurrenceRule | None = None,
        metadata: dict[str, Any] | None = None,
        clear_end: bool = False,
    ) -> CalendarEvent | None:
        _validate(category, EVENT_CATEGORIES, "event category")
        if recurrence is not None:
            try:
                recurrence.validate()
            except ValueError as err:
                raise ServiceError(str(err)) from err

        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            event = await repo.update_event(
                event_id,
                title=title,
                description=description,
                location=location,
                category=category,
                starts_at=starts_at,
                ends_at=ends_at,
                all_day=all_day,
                recurrence_json=(
                    json.dumps(recurrence.as_dict()) if recurrence is not None else None
                ),
                meta_json=json.dumps(metadata) if metadata is not None else None,
                clear_end=clear_end,
            )
            if event is None:
                return None
            if event.ends_at is not None and event.ends_at < event.starts_at:
                raise ServiceError("An event cannot end before it starts.")
            calendar_id = event.calendar_id
            workspace_id = await repo.workspace_of(calendar_id) or ""
        await self._publish_event(event_id, calendar_id, workspace_id, action="updated")
        return await self.get_event(event_id)

    async def delete_event(self, event_id: str) -> bool:
        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            event = await repo.get_event(event_id)
            if event is None:
                return False
            calendar_id = event.calendar_id
            workspace_id = await repo.workspace_of(calendar_id) or ""
            await repo.delete_event(event_id)
        await self._publish_event(event_id, calendar_id, workspace_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Recurrence
    # ------------------------------------------------------------------
    async def recurrence_of(self, event_id: str) -> RecurrenceRule:
        return decode_recurrence((await self.require_event(event_id)).recurrence_json)

    async def metadata_of(self, event_id: str) -> dict[str, Any]:
        return decode_metadata((await self.require_event(event_id)).meta_json)

    # ------------------------------------------------------------------
    # Search hook
    # ------------------------------------------------------------------
    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """Events *and* calendars, in one source: a user searching
        "standup" wants the meeting, and one searching "Work" wants the
        calendar, and making them pick a source first would be the tool
        asking the user to know its schema."""
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            repo = CalendarRepository(sess)  # type: ignore[arg-type]
            events = await repo.search_events(query, limit=top_k)
            calendars = await repo.search_calendars(query, limit=top_k)

        results = [
            SearchResult(
                id=event.id,
                title=event.title,
                content=event.description,
                source="calendar",
                score=1.0,
                uri=f"event://{event.id}",
                metadata={
                    "kind": "event",
                    "calendar_id": event.calendar_id,
                    "category": event.category,
                    "starts_at": event.starts_at.isoformat() if event.starts_at else None,
                    "location": event.location,
                },
            )
            for event in events
        ]
        results.extend(
            SearchResult(
                id=calendar.id,
                title=calendar.name,
                content=calendar.description,
                source="calendar",
                # A container is a weaker hit than the thing inside it.
                score=0.7,
                uri=f"calendar://{calendar.id}",
                metadata={"kind": "calendar", "workspace_id": calendar.workspace_id},
            )
            for calendar in calendars
        )
        return results[:top_k]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _require_workspace(self, workspace_id: str) -> None:
        if self._workspaces is not None:
            await self._workspaces.require_workspace(workspace_id)

    async def _publish_calendar(self, calendar_id: str, workspace_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import CalendarUpdatedEvent

        await self._event_bus.publish(
            CalendarUpdatedEvent(calendar_id=calendar_id, workspace_id=workspace_id, action=action)
        )

    async def _publish_event(
        self, event_id: str, calendar_id: str, workspace_id: str, *, action: str
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import CalendarEventUpdatedEvent

        await self._event_bus.publish(
            CalendarEventUpdatedEvent(
                event_id=event_id,
                calendar_id=calendar_id,
                workspace_id=workspace_id,
                action=action,
            )
        )


def decode_recurrence(raw: str) -> RecurrenceRule:
    try:
        payload: Any = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return RecurrenceRule()
    return RecurrenceRule.from_dict(payload if isinstance(payload, dict) else {})


def decode_metadata(raw: str) -> dict[str, Any]:
    try:
        payload: Any = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _validate(value: str | None, allowed: frozenset[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")
