"""Scheduler API -- Milestone 7 Phase 6 (Scheduler MVP).

``/api/v1/schedules`` -- thin REST over ``ScheduleService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses.

**Seven routes**, matching the Logic Contract's own smallest-coherent-
surface decision (§14): create/list/retrieve/enable/disable/delete a
schedule, plus its execution history. A separate ``.../cancel`` route
was evaluated there and deliberately dropped as redundant with
``enable``/``disable``/``DELETE``.

**Status-code convention, mirroring ``routes/smart_home_memory.py``'s
own exception-type dispatch**: ``SchedulerPermissionError`` -> 400;
``ScheduleNotFoundError`` -> 404; any other ``ServiceError`` (a
malformed cron expression, an interval below the 60s floor, an unknown
timezone, a malformed step) -> 400.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.schedule_service import ScheduleService

router = APIRouter(tags=["schedules"], dependencies=[Depends(get_current_session)])


class WorkflowStepRequest(BaseModel):
    kind: str
    instruction: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = {}
    depends_on: list[str] = []
    label: str = ""


class CreateScheduleRequest(BaseModel):
    name: str
    steps: list[WorkflowStepRequest]
    kind: str
    description: str = ""
    interval_seconds: float = 0.0
    cron_expression: str = ""
    timezone: str | None = None
    enabled: bool = True


def _service(request: Request) -> ScheduleService:
    return cast("ScheduleService", request.app.state.container.schedule_service())


def _handle(err: Exception) -> HTTPException:
    from jarvis.services.schedule_service import ScheduleNotFoundError, SchedulerPermissionError

    if isinstance(err, SchedulerPermissionError):
        return HTTPException(status_code=400, detail=str(err))
    if isinstance(err, ScheduleNotFoundError):
        return HTTPException(status_code=404, detail=str(err))
    return HTTPException(status_code=400, detail=str(err))


@router.post("/schedules", response_model=Envelope[dict[str, Any]])
async def create_schedule(
    body: CreateScheduleRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Creates one dedicated workflow + schedule pair (Logic Contract
    §5 -- no standalone workflow-authoring API in this phase). Permission
    not granted, invalid kind/interval/cron/timezone, or a malformed
    step -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).create_schedule(
            name=body.name,
            steps=[s.model_dump() for s in body.steps],
            kind=body.kind,
            description=body.description,
            interval_seconds=body.interval_seconds,
            cron_expression=body.cron_expression,
            timezone=body.timezone,
            enabled=body.enabled,
        )
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result, meta={"schedule_id": result["id"]})


@router.get("/schedules", response_model=Envelope[list[dict[str, Any]]])
async def list_schedules(
    request: Request, enabled_only: bool = False
) -> Envelope[list[dict[str, Any]]]:
    """Permission not granted -> 400. Never a 404 -- an empty result is
    a normal, valid list."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_schedules(enabled_only=enabled_only)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/schedules/{schedule_id}", response_model=Envelope[dict[str, Any]])
async def get_schedule(schedule_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Unknown schedule -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).get_schedule(schedule_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.post("/schedules/{schedule_id}/enable", response_model=Envelope[dict[str, Any]])
async def enable_schedule(schedule_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).enable_schedule(schedule_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.post("/schedules/{schedule_id}/disable", response_model=Envelope[dict[str, Any]])
async def disable_schedule(schedule_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).disable_schedule(schedule_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.delete("/schedules/{schedule_id}", response_model=Envelope[dict[str, Any]])
async def delete_schedule(schedule_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        deleted = await _service(request).delete_schedule(schedule_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope({"schedule_id": schedule_id, "deleted": deleted})


@router.get("/schedules/{schedule_id}/executions", response_model=Envelope[list[dict[str, Any]]])
async def list_executions(
    schedule_id: str, request: Request, limit: int = 50
) -> Envelope[list[dict[str, Any]]]:
    """Unknown schedule -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_executions(schedule_id, limit=limit)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})
