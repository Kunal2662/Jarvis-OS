"""Productivity API -- Milestone 11 Task Group B.

``/api/v1/tasks``, ``/api/v1/calendar`` and ``/api/v1/reminders`` --
thin REST over ``TaskService`` / ``CalendarService`` /
``ReminderService``, plus the composed reads their managers provide.
Same ``Depends(get_current_session)`` Bearer auth and ``{data, meta}``
envelope as every resource router since M9 Task Group E; this one owns
no state and no logic of its own.

One module for three domains, mirroring ``workspaces.py``: they ship
together, share every convention, and a reader comparing a task payload
to an event payload should not have to open two files. The three
prefixes keep the surfaces distinct.

**No scheduling endpoints.** ``GET /reminders/due`` reports which
reminders have come due and changes nothing -- there is no "fire", no
"send", and no side effect. Delivery is M7's Scheduler (Phase 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.calendar_service import CalendarService
    from jarvis.services.productivity_managers import (
        CalendarManager,
        ReminderManager,
        TaskManager,
    )
    from jarvis.services.reminder_service import ReminderService
    from jarvis.services.task_service import TaskService

router = APIRouter(tags=["productivity"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class RecurrencePayload(BaseModel):
    """The stored repeat rule. Deliberately not an RRULE string -- see
    ``domain/productivity/models.py`` for why this build names its four
    frequencies instead of claiming RFC 5545."""

    frequency: str = ""
    interval: int = 1
    count: int | None = None
    until: datetime | None = None


class CreateTaskRequest(BaseModel):
    workspace_id: str
    title: str
    description: str = ""
    project_id: str | None = None
    priority: str = "normal"
    due_at: datetime | None = None
    tags: list[str] = []


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    tags: list[str] | None = None
    project_id: str | None = None
    clear_project: bool = False
    clear_due: bool = False


class CreateCalendarRequest(BaseModel):
    workspace_id: str
    name: str
    description: str = ""
    color: str = ""
    is_default: bool = False


class UpdateCalendarRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    color: str | None = None
    is_default: bool | None = None


class CreateEventRequest(BaseModel):
    calendar_id: str
    title: str
    starts_at: datetime
    description: str = ""
    location: str = ""
    category: str = "general"
    ends_at: datetime | None = None
    all_day: bool = False
    recurrence: RecurrencePayload | None = None
    metadata: dict[str, Any] = {}


class UpdateEventRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    location: str | None = None
    category: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    all_day: bool | None = None
    recurrence: RecurrencePayload | None = None
    metadata: dict[str, Any] | None = None
    clear_end: bool = False


class CreateReminderRequest(BaseModel):
    workspace_id: str
    title: str
    remind_at: datetime
    notes: str = ""
    task_id: str | None = None
    event_id: str | None = None
    recurrence: RecurrencePayload | None = None


class UpdateReminderRequest(BaseModel):
    title: str | None = None
    notes: str | None = None
    remind_at: datetime | None = None
    status: str | None = None
    recurrence: RecurrencePayload | None = None


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _tasks(request: Request) -> TaskService:
    return cast("TaskService", request.app.state.container.task_service())


def _calendar(request: Request) -> CalendarService:
    return cast("CalendarService", request.app.state.container.calendar_service())


def _reminders(request: Request) -> ReminderService:
    return cast("ReminderService", request.app.state.container.reminder_service())


def _task_manager(request: Request) -> TaskManager:
    return cast("TaskManager", request.app.state.container.task_manager())


def _calendar_manager(request: Request) -> CalendarManager:
    return cast("CalendarManager", request.app.state.container.calendar_manager())


def _reminder_manager(request: Request) -> ReminderManager:
    return cast("ReminderManager", request.app.state.container.reminder_manager())


def _rule(payload: RecurrencePayload | None) -> Any:
    from jarvis.domain.productivity.models import RecurrenceRule

    if payload is None:
        return None
    return RecurrenceRule(
        frequency=payload.frequency,
        interval=payload.interval,
        count=payload.count,
        until=payload.until,
    )


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment else None


def _task_payload(task: Any) -> dict[str, Any]:
    from jarvis.services.task_service import decode_tags

    return {
        "id": task.id,
        "workspace_id": task.workspace_id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status,
        "priority": task.priority,
        "due_at": _iso(task.due_at),
        "tags": decode_tags(task.tags_json),
        "completed_at": _iso(task.completed_at),
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
    }


def _calendar_payload(calendar: Any) -> dict[str, Any]:
    return {
        "id": calendar.id,
        "workspace_id": calendar.workspace_id,
        "name": calendar.name,
        "description": calendar.description,
        "color": calendar.color,
        "is_default": calendar.is_default,
        "created_at": _iso(calendar.created_at),
        "updated_at": _iso(calendar.updated_at),
    }


def _event_payload(event: Any) -> dict[str, Any]:
    from jarvis.services.calendar_service import decode_metadata, decode_recurrence

    return {
        "id": event.id,
        "calendar_id": event.calendar_id,
        "title": event.title,
        "description": event.description,
        "location": event.location,
        "category": event.category,
        "starts_at": _iso(event.starts_at),
        "ends_at": _iso(event.ends_at),
        "all_day": event.all_day,
        "recurrence": decode_recurrence(event.recurrence_json).as_dict(),
        "metadata": decode_metadata(event.meta_json),
        "created_at": _iso(event.created_at),
        "updated_at": _iso(event.updated_at),
    }


def _reminder_payload(reminder: Any) -> dict[str, Any]:
    from jarvis.services.reminder_service import decode_recurrence

    return {
        "id": reminder.id,
        "workspace_id": reminder.workspace_id,
        "task_id": reminder.task_id,
        "event_id": reminder.event_id,
        "title": reminder.title,
        "notes": reminder.notes,
        "remind_at": _iso(reminder.remind_at),
        "status": reminder.status,
        "recurrence": decode_recurrence(reminder.recurrence_json).as_dict(),
        "created_at": _iso(reminder.created_at),
        "updated_at": _iso(reminder.updated_at),
    }


def _bad_request(err: Exception) -> HTTPException:
    """A ``ServiceError`` means the caller asked for something invalid --
    an empty title, an unknown status, an event ending before it starts.
    400, not 500: nothing broke."""
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------
@router.post("/tasks", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_task(body: CreateTaskRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        task = await _tasks(request).create_task(
            body.workspace_id,
            body.title,
            description=body.description,
            project_id=body.project_id,
            priority=body.priority,
            due_at=body.due_at,
            tags=body.tags,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_task_payload(task), meta={"created": True})


@router.get("/tasks", response_model=Envelope[list[dict[str, Any]]])
async def list_tasks(
    request: Request,
    workspace_id: str | None = None,
    project_id: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    tag: str | None = None,
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        tasks = await _tasks(request).list_tasks(
            workspace_id=workspace_id,
            project_id=project_id,
            status=status,
            priority=priority,
            tag=tag,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    payload = [_task_payload(task) for task in tasks]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/tasks/agenda", response_model=Envelope[dict[str, Any]])
async def task_agenda(
    request: Request, workspace_id: str, horizon_days: int = 7
) -> Envelope[dict[str, Any]]:
    """Overdue, due-soon and status counts for one workspace, via
    ``TaskManager``. Declared before ``/tasks/{task_id}`` so the literal
    path wins the match."""
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(
            await _task_manager(request).agenda(workspace_id, horizon_days=horizon_days)
        )
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get("/tasks/{task_id}", response_model=Envelope[dict[str, Any]])
async def get_task(task_id: str, request: Request) -> Envelope[dict[str, Any]]:
    task = await _tasks(request).get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return envelope(_task_payload(task))


@router.get("/tasks/{task_id}/context", response_model=Envelope[dict[str, Any]])
async def task_context(task_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _task_manager(request).context(task_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.patch("/tasks/{task_id}", response_model=Envelope[dict[str, Any]])
async def update_task(
    task_id: str, body: UpdateTaskRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        task = await _tasks(request).update_task(
            task_id,
            title=body.title,
            description=body.description,
            status=body.status,
            priority=body.priority,
            due_at=body.due_at,
            tags=body.tags,
            project_id=body.project_id,
            clear_project=body.clear_project,
            clear_due=body.clear_due,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    return envelope(_task_payload(task))


@router.delete("/tasks/{task_id}", status_code=204)
async def delete_task(task_id: str, request: Request) -> None:
    if not await _tasks(request).delete_task(task_id):
        raise HTTPException(status_code=404, detail="Task not found.")


# ---------------------------------------------------------------------------
# Calendars + events
# ---------------------------------------------------------------------------
@router.post("/calendar/calendars", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_calendar(
    body: CreateCalendarRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        calendar = await _calendar(request).create_calendar(
            body.workspace_id,
            body.name,
            description=body.description,
            color=body.color,
            is_default=body.is_default,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_calendar_payload(calendar), meta={"created": True})


@router.get("/calendar/calendars", response_model=Envelope[list[dict[str, Any]]])
async def list_calendars(
    request: Request, workspace_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    calendars = await _calendar(request).list_calendars(workspace_id=workspace_id)
    payload = [_calendar_payload(calendar) for calendar in calendars]
    return envelope(payload, meta={"count": len(payload)})


@router.patch("/calendar/calendars/{calendar_id}", response_model=Envelope[dict[str, Any]])
async def update_calendar(
    calendar_id: str, body: UpdateCalendarRequest, request: Request
) -> Envelope[dict[str, Any]]:
    calendar = await _calendar(request).update_calendar(
        calendar_id,
        name=body.name,
        description=body.description,
        color=body.color,
        is_default=body.is_default,
    )
    if calendar is None:
        raise HTTPException(status_code=404, detail="Calendar not found.")
    return envelope(_calendar_payload(calendar))


@router.delete("/calendar/calendars/{calendar_id}", status_code=204)
async def delete_calendar(calendar_id: str, request: Request) -> None:
    """Deletes the calendar and its events -- unlike deleting a project,
    which keeps its notes. See ``CalendarService.delete_calendar``."""
    if not await _calendar(request).delete_calendar(calendar_id):
        raise HTTPException(status_code=404, detail="Calendar not found.")


@router.post("/calendar/events", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_event(body: CreateEventRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        event = await _calendar(request).create_event(
            body.calendar_id,
            body.title,
            body.starts_at,
            description=body.description,
            location=body.location,
            category=body.category,
            ends_at=body.ends_at,
            all_day=body.all_day,
            recurrence=_rule(body.recurrence),
            metadata=body.metadata,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_event_payload(event), meta={"created": True})


@router.get("/calendar/events", response_model=Envelope[list[dict[str, Any]]])
async def list_events(
    request: Request,
    calendar_id: str | None = None,
    workspace_id: str | None = None,
    category: str | None = None,
) -> Envelope[list[dict[str, Any]]]:
    """Stored events. For a date range with recurrences expanded into
    concrete occurrences, use ``/calendar/occurrences``."""
    from jarvis.core.exceptions import ServiceError

    try:
        events = await _calendar(request).list_events(
            calendar_id=calendar_id, workspace_id=workspace_id, category=category
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    payload = [_event_payload(event) for event in events]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/calendar/occurrences", response_model=Envelope[list[dict[str, Any]]])
async def list_occurrences(
    request: Request,
    window_start: datetime,
    window_end: datetime,
    workspace_id: str | None = None,
    calendar_id: str | None = None,
) -> Envelope[list[dict[str, Any]]]:
    """Recurring events expanded into the concrete datetimes that fall
    inside the window -- the view a calendar renders.

    Expansion, not scheduling: this computes datetimes and returns
    them.
    """
    rows = await _calendar_manager(request).occurrences(
        window_start=window_start,
        window_end=window_end,
        workspace_id=workspace_id,
        calendar_id=calendar_id,
    )
    return envelope(rows, meta={"count": len(rows)})


@router.get("/calendar/agenda", response_model=Envelope[dict[str, Any]])
async def calendar_agenda(
    request: Request, workspace_id: str, horizon_days: int = 7
) -> Envelope[dict[str, Any]]:
    return envelope(
        await _calendar_manager(request).agenda(workspace_id, horizon_days=horizon_days)
    )


@router.get("/calendar/events/{event_id}", response_model=Envelope[dict[str, Any]])
async def get_event(event_id: str, request: Request) -> Envelope[dict[str, Any]]:
    event = await _calendar(request).get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return envelope(_event_payload(event))


@router.patch("/calendar/events/{event_id}", response_model=Envelope[dict[str, Any]])
async def update_event(
    event_id: str, body: UpdateEventRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        event = await _calendar(request).update_event(
            event_id,
            title=body.title,
            description=body.description,
            location=body.location,
            category=body.category,
            starts_at=body.starts_at,
            ends_at=body.ends_at,
            all_day=body.all_day,
            recurrence=_rule(body.recurrence),
            metadata=body.metadata,
            clear_end=body.clear_end,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return envelope(_event_payload(event))


@router.delete("/calendar/events/{event_id}", status_code=204)
async def delete_event(event_id: str, request: Request) -> None:
    if not await _calendar(request).delete_event(event_id):
        raise HTTPException(status_code=404, detail="Event not found.")


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------
@router.post("/reminders", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_reminder(
    body: CreateReminderRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        reminder = await _reminders(request).create_reminder(
            body.workspace_id,
            body.title,
            body.remind_at,
            notes=body.notes,
            task_id=body.task_id,
            event_id=body.event_id,
            recurrence=_rule(body.recurrence),
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_reminder_payload(reminder), meta={"created": True})


@router.get("/reminders", response_model=Envelope[list[dict[str, Any]]])
async def list_reminders(
    request: Request,
    workspace_id: str | None = None,
    status: str | None = None,
    task_id: str | None = None,
    event_id: str | None = None,
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        reminders = await _reminders(request).list_reminders(
            workspace_id=workspace_id, status=status, task_id=task_id, event_id=event_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    payload = [_reminder_payload(reminder) for reminder in reminders]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/reminders/due", response_model=Envelope[dict[str, Any]])
async def reminders_due(
    request: Request, workspace_id: str | None = None
) -> Envelope[dict[str, Any]]:
    """Which reminders have come due, with their targets resolved.

    **Reports; does not deliver.** Calling this sends nothing and
    changes no status -- every reminder listed is still ``pending``
    afterwards. Delivery is M7's Scheduler (Phase 6), and the response
    says so in ``data.detail`` rather than leaving a caller to assume.
    """
    return envelope(
        await _reminder_manager(request).due_digest(
            now=datetime.now(UTC), workspace_id=workspace_id
        )
    )


@router.get("/reminders/{reminder_id}", response_model=Envelope[dict[str, Any]])
async def get_reminder(reminder_id: str, request: Request) -> Envelope[dict[str, Any]]:
    reminder = await _reminders(request).get_reminder(reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return envelope(_reminder_payload(reminder))


@router.get("/reminders/{reminder_id}/context", response_model=Envelope[dict[str, Any]])
async def reminder_context(reminder_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _reminder_manager(request).context(reminder_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.patch("/reminders/{reminder_id}", response_model=Envelope[dict[str, Any]])
async def update_reminder(
    reminder_id: str, body: UpdateReminderRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        reminder = await _reminders(request).update_reminder(
            reminder_id,
            title=body.title,
            notes=body.notes,
            remind_at=body.remind_at,
            status=body.status,
            recurrence=_rule(body.recurrence),
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found.")
    return envelope(_reminder_payload(reminder))


@router.delete("/reminders/{reminder_id}", status_code=204)
async def delete_reminder(reminder_id: str, request: Request) -> None:
    if not await _reminders(request).delete_reminder(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found.")
