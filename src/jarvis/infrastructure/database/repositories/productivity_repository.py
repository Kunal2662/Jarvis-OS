"""Productivity repositories -- Milestone 11 Task Group B.

``TaskRepository`` / ``CalendarRepository`` / ``ReminderRepository``,
following ``WorkspaceRepository``'s shape exactly: constructed with an
``AsyncSession``, no transaction management of its own (the service owns
that via ``db.session()``), and ``flush()`` rather than ``commit()``
after an insert.

``CalendarRepository`` owns *both* calendars and their events, unlike
Task Group A where each entity got its own class. An event has no
identity outside a calendar -- there is no "list every event" that is
not really "list a calendar's events" -- so splitting them would produce
a class whose every method takes a ``calendar_id``. Workspaces and
projects were genuinely independently useful; these are not.

Methods are named per entity (``list_tasks``, not ``list``) for the
reason Task Group A discovered the hard way: a method called ``list``
shadows the builtin inside the class body, and ``-> list[Task]`` then
resolves to the method rather than the type.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from jarvis.infrastructure.database.models import (
    Calendar,
    CalendarEvent,
    Reminder,
    Task,
)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        title: str,
        *,
        description: str = "",
        project_id: str | None = None,
        priority: str = "normal",
        due_at: datetime | None = None,
        tags_json: str = "[]",
    ) -> Task:
        task = Task(
            workspace_id=workspace_id,
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            due_at=due_at,
            tags_json=tags_json,
        )
        self._s.add(task)
        await self._s.flush()
        return task

    async def get(self, task_id: str) -> Task | None:
        return await self._s.get(Task, task_id)

    async def list_tasks(
        self,
        *,
        workspace_id: str | None = None,
        project_id: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Task]:
        """Ordered by due date (soonest first, undated last), then most
        recently updated -- the order a task list is read in, applied
        once here rather than by each caller.

        ``due_at.is_(None)`` sorts last explicitly: SQLite would put
        NULLs first, which would bury every dated task under every
        undated one.
        """
        stmt = (
            select(Task)
            .order_by(Task.due_at.is_(None), Task.due_at.asc(), Task.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if workspace_id is not None:
            stmt = stmt.where(Task.workspace_id == workspace_id)
        if project_id is not None:
            stmt = stmt.where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if priority is not None:
            stmt = stmt.where(Task.priority == priority)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_due_before(
        self, moment: datetime, *, workspace_id: str | None = None, limit: int = 200
    ) -> list[Task]:
        """Open tasks due at or before *moment*. Backs the agenda view;
        ``done``/``cancelled`` are excluded because a completed task is
        not "due"."""
        stmt = (
            select(Task)
            .where(
                Task.due_at.is_not(None),
                Task.due_at <= moment,
                Task.status.notin_(("done", "cancelled")),
            )
            .order_by(Task.due_at.asc())
            .limit(limit)
        )
        if workspace_id is not None:
            stmt = stmt.where(Task.workspace_id == workspace_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        status: str | None = None,
        priority: str | None = None,
        due_at: datetime | None = None,
        tags_json: str | None = None,
        project_id: str | None = None,
        completed_at: datetime | None = None,
        clear_project: bool = False,
        clear_due: bool = False,
    ) -> Task | None:
        """Partial update -- ``None`` means "leave alone". ``clear_*``
        flags exist because ``None`` is already taken by that
        convention, and "remove the due date" is a real operation that
        would otherwise be unexpressible (the same reason
        ``NoteRepository.update`` has ``clear_project``)."""
        task = await self.get(task_id)
        if task is None:
            return None
        if title is not None:
            task.title = title
        if description is not None:
            task.description = description
        if status is not None:
            task.status = status
        if priority is not None:
            task.priority = priority
        if clear_due:
            task.due_at = None
        elif due_at is not None:
            task.due_at = due_at
        if tags_json is not None:
            task.tags_json = tags_json
        if clear_project:
            task.project_id = None
        elif project_id is not None:
            task.project_id = project_id
        # Set explicitly by the service on the done/undone transition,
        # so this stays a plain assignment rather than inferring intent.
        task.completed_at = completed_at if status is not None else task.completed_at
        return task

    async def delete(self, task_id: str) -> bool:
        task = await self.get(task_id)
        if task is None:
            return False
        await self._s.delete(task)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Task]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Task)
            .where(
                or_(
                    func.lower(Task.title).like(pattern),
                    func.lower(Task.description).like(pattern),
                    func.lower(Task.tags_json).like(pattern),
                )
            )
            .order_by(Task.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def counts_by_status(self, workspace_id: str) -> dict[str, int]:
        stmt = (
            select(Task.status, func.count())
            .where(Task.workspace_id == workspace_id)
            .group_by(Task.status)
        )
        return {row[0]: int(row[1]) for row in (await self._s.execute(stmt)).all()}


class CalendarRepository:
    """Calendars *and* their events -- see the module docstring."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # ---- Calendars ---------------------------------------------------
    async def add_calendar(
        self,
        workspace_id: str,
        name: str,
        *,
        description: str = "",
        color: str = "",
        is_default: bool = False,
    ) -> Calendar:
        calendar = Calendar(
            workspace_id=workspace_id,
            name=name,
            description=description,
            color=color,
            is_default=is_default,
        )
        self._s.add(calendar)
        await self._s.flush()
        return calendar

    async def get_calendar(self, calendar_id: str) -> Calendar | None:
        return await self._s.get(Calendar, calendar_id)

    async def list_calendars(
        self, *, workspace_id: str | None = None, limit: int = 200
    ) -> list[Calendar]:
        stmt = (
            select(Calendar)
            .order_by(Calendar.is_default.desc(), Calendar.created_at.asc())
            .limit(limit)
        )
        if workspace_id is not None:
            stmt = stmt.where(Calendar.workspace_id == workspace_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def default_calendar(self, workspace_id: str) -> Calendar | None:
        stmt = (
            select(Calendar)
            .where(Calendar.workspace_id == workspace_id, Calendar.is_default.is_(True))
            .limit(1)
        )
        return (await self._s.execute(stmt)).scalars().first()

    async def update_calendar(
        self,
        calendar_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        color: str | None = None,
        is_default: bool | None = None,
    ) -> Calendar | None:
        calendar = await self.get_calendar(calendar_id)
        if calendar is None:
            return None
        if name is not None:
            calendar.name = name
        if description is not None:
            calendar.description = description
        if color is not None:
            calendar.color = color
        if is_default is not None:
            calendar.is_default = is_default
        return calendar

    async def clear_default(self, workspace_id: str, *, except_id: str = "") -> None:
        """Only one calendar per workspace may be the default. Enforced
        here rather than by a partial unique index, because SQLite's
        support for those is version-dependent and this is a single
        cheap UPDATE on a small table."""
        stmt = select(Calendar).where(
            Calendar.workspace_id == workspace_id, Calendar.is_default.is_(True)
        )
        for calendar in (await self._s.execute(stmt)).scalars().all():
            if calendar.id != except_id:
                calendar.is_default = False

    async def delete_calendar(self, calendar_id: str) -> bool:
        calendar = await self.get_calendar(calendar_id)
        if calendar is None:
            return False
        await self._s.delete(calendar)
        return True

    async def search_calendars(self, query: str, *, limit: int = 10) -> list[Calendar]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Calendar)
            .where(
                or_(
                    func.lower(Calendar.name).like(pattern),
                    func.lower(Calendar.description).like(pattern),
                )
            )
            .order_by(Calendar.updated_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    # ---- Events ------------------------------------------------------
    async def add_event(
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
        recurrence_json: str = "{}",
        meta_json: str = "{}",
    ) -> CalendarEvent:
        event = CalendarEvent(
            calendar_id=calendar_id,
            title=title,
            description=description,
            location=location,
            category=category,
            starts_at=starts_at,
            ends_at=ends_at,
            all_day=all_day,
            recurrence_json=recurrence_json,
            meta_json=meta_json,
        )
        self._s.add(event)
        await self._s.flush()
        return event

    async def get_event(self, event_id: str) -> CalendarEvent | None:
        return await self._s.get(CalendarEvent, event_id)

    async def list_events(
        self,
        *,
        calendar_id: str | None = None,
        workspace_id: str | None = None,
        category: str | None = None,
        starts_after: datetime | None = None,
        starts_before: datetime | None = None,
        limit: int = 200,
    ) -> list[CalendarEvent]:
        """Filtering by workspace joins through ``calendars`` rather than
        reading a denormalized column -- the calendar owns that
        relationship, and copying it onto the event would create a
        second source of truth (see ``CalendarEvent``'s docstring).

        The time window filters on the event's *stored* start only. A
        recurring event whose first occurrence predates the window still
        matches, because its later occurrences may fall inside it;
        narrowing to the actual occurrences is the caller's job via
        ``RecurrenceRule.occurrences``, which is where that logic lives.
        """
        stmt = select(CalendarEvent).order_by(CalendarEvent.starts_at.asc()).limit(limit)
        if calendar_id is not None:
            stmt = stmt.where(CalendarEvent.calendar_id == calendar_id)
        if workspace_id is not None:
            stmt = stmt.join(Calendar, Calendar.id == CalendarEvent.calendar_id).where(
                Calendar.workspace_id == workspace_id
            )
        if category is not None:
            stmt = stmt.where(CalendarEvent.category == category)
        if starts_after is not None:
            stmt = stmt.where(CalendarEvent.starts_at >= starts_after)
        if starts_before is not None:
            stmt = stmt.where(CalendarEvent.starts_at <= starts_before)
        return list((await self._s.execute(stmt)).scalars().all())

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
        recurrence_json: str | None = None,
        meta_json: str | None = None,
        clear_end: bool = False,
    ) -> CalendarEvent | None:
        event = await self.get_event(event_id)
        if event is None:
            return None
        if title is not None:
            event.title = title
        if description is not None:
            event.description = description
        if location is not None:
            event.location = location
        if category is not None:
            event.category = category
        if starts_at is not None:
            event.starts_at = starts_at
        if clear_end:
            event.ends_at = None
        elif ends_at is not None:
            event.ends_at = ends_at
        if all_day is not None:
            event.all_day = all_day
        if recurrence_json is not None:
            event.recurrence_json = recurrence_json
        if meta_json is not None:
            event.meta_json = meta_json
        return event

    async def delete_event(self, event_id: str) -> bool:
        event = await self.get_event(event_id)
        if event is None:
            return False
        await self._s.delete(event)
        return True

    async def search_events(self, query: str, *, limit: int = 10) -> list[CalendarEvent]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(CalendarEvent)
            .where(
                or_(
                    func.lower(CalendarEvent.title).like(pattern),
                    func.lower(CalendarEvent.description).like(pattern),
                    func.lower(CalendarEvent.location).like(pattern),
                )
            )
            .order_by(CalendarEvent.starts_at.desc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())

    async def workspace_of(self, calendar_id: str) -> str | None:
        """The owning workspace id, for events that need to report one
        without the caller loading the whole calendar.

        ``scalar()`` is typed ``Any``, so the result is narrowed here
        rather than returned straight through -- an unknown calendar
        genuinely yields ``None``, and a caller should be able to trust
        the annotation (the same reasoning as
        ``NoteRepository.last_activity_at``)."""
        value = await self._s.scalar(
            select(Calendar.workspace_id).where(Calendar.id == calendar_id)
        )
        return value if isinstance(value, str) else None


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def add(
        self,
        workspace_id: str,
        title: str,
        remind_at: datetime,
        *,
        notes: str = "",
        task_id: str | None = None,
        event_id: str | None = None,
        recurrence_json: str = "{}",
    ) -> Reminder:
        reminder = Reminder(
            workspace_id=workspace_id,
            title=title,
            remind_at=remind_at,
            notes=notes,
            task_id=task_id,
            event_id=event_id,
            recurrence_json=recurrence_json,
        )
        self._s.add(reminder)
        await self._s.flush()
        return reminder

    async def get(self, reminder_id: str) -> Reminder | None:
        return await self._s.get(Reminder, reminder_id)

    async def list_reminders(
        self,
        *,
        workspace_id: str | None = None,
        status: str | None = None,
        task_id: str | None = None,
        event_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> list[Reminder]:
        stmt = select(Reminder).order_by(Reminder.remind_at.asc()).limit(limit).offset(offset)
        if workspace_id is not None:
            stmt = stmt.where(Reminder.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(Reminder.status == status)
        if task_id is not None:
            stmt = stmt.where(Reminder.task_id == task_id)
        if event_id is not None:
            stmt = stmt.where(Reminder.event_id == event_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def list_due_before(
        self, moment: datetime, *, workspace_id: str | None = None, limit: int = 200
    ) -> list[Reminder]:
        """Pending reminders whose time has arrived.

        A *query*, not a trigger: this reports which reminders are due,
        and nothing in this task group acts on the answer. Firing them
        is M7's Scheduler (Phase 6).
        """
        stmt = (
            select(Reminder)
            .where(Reminder.remind_at <= moment, Reminder.status == "pending")
            .order_by(Reminder.remind_at.asc())
            .limit(limit)
        )
        if workspace_id is not None:
            stmt = stmt.where(Reminder.workspace_id == workspace_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def update(
        self,
        reminder_id: str,
        *,
        title: str | None = None,
        notes: str | None = None,
        remind_at: datetime | None = None,
        status: str | None = None,
        recurrence_json: str | None = None,
    ) -> Reminder | None:
        reminder = await self.get(reminder_id)
        if reminder is None:
            return None
        if title is not None:
            reminder.title = title
        if notes is not None:
            reminder.notes = notes
        if remind_at is not None:
            reminder.remind_at = remind_at
        if status is not None:
            reminder.status = status
        if recurrence_json is not None:
            reminder.recurrence_json = recurrence_json
        return reminder

    async def delete(self, reminder_id: str) -> bool:
        reminder = await self.get(reminder_id)
        if reminder is None:
            return False
        await self._s.delete(reminder)
        return True

    async def search(self, query: str, *, limit: int = 10) -> list[Reminder]:
        pattern = f"%{query.lower()}%"
        stmt = (
            select(Reminder)
            .where(
                or_(
                    func.lower(Reminder.title).like(pattern),
                    func.lower(Reminder.notes).like(pattern),
                )
            )
            .order_by(Reminder.remind_at.asc())
            .limit(limit)
        )
        return list((await self._s.execute(stmt)).scalars().all())
