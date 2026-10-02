"""Home Automation API -- M7 (event-based triggers).

``/api/v1/home-automation`` -- thin REST over ``HomeAutomationService``,
the same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses.

**Eight routes**, matching the Logic Contract's own smallest-coherent-
surface decision (§22): create/list/retrieve/enable/disable/delete an
automation, plus its execution history, plus a manual test run (the one
capability beyond Scheduler's own 7-route precedent this slice's MVP
scope explicitly requires). No ``PATCH``/update route -- matching
Scheduler's own precedent exactly; changing an automation means delete
+ recreate.

**Status-code convention, mirroring ``routes/schedules.py``'s own
exception-type dispatch**: ``HomeAutomationPermissionError`` -> 400;
``AutomationTriggerNotFoundError`` -> 404; any other ``ServiceError``
(a malformed step, an empty name/device_id/to_status) -> 400.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.home_automation_service import HomeAutomationService

router = APIRouter(tags=["home-automation"], dependencies=[Depends(get_current_session)])


class WorkflowStepRequest(BaseModel):
    kind: str
    instruction: str = ""
    tool_name: str = ""
    tool_args: dict[str, Any] = {}
    depends_on: list[str] = []
    label: str = ""


class CreateAutomationRequest(BaseModel):
    name: str
    device_id: str
    to_status: str
    steps: list[WorkflowStepRequest]
    from_status: str = ""
    description: str = ""
    enabled: bool = True


def _service(request: Request) -> HomeAutomationService:
    return cast("HomeAutomationService", request.app.state.container.home_automation_service())


def _handle(err: Exception) -> HTTPException:
    from jarvis.services.home_automation_service import (
        AutomationTriggerNotFoundError,
        HomeAutomationPermissionError,
    )

    if isinstance(err, HomeAutomationPermissionError):
        return HTTPException(status_code=400, detail=str(err))
    if isinstance(err, AutomationTriggerNotFoundError):
        return HTTPException(status_code=404, detail=str(err))
    return HTTPException(status_code=400, detail=str(err))


@router.post("/home-automation", response_model=Envelope[dict[str, Any]])
async def create_automation(
    body: CreateAutomationRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Creates one dedicated workflow + automation-trigger pair.
    Permission not granted, an empty name/device_id/to_status, or a
    malformed step -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).create_automation(
            name=body.name,
            device_id=body.device_id,
            to_status=body.to_status,
            steps=[s.model_dump() for s in body.steps],
            from_status=body.from_status,
            description=body.description,
            enabled=body.enabled,
        )
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result, meta={"automation_id": result["id"]})


@router.get("/home-automation", response_model=Envelope[list[dict[str, Any]]])
async def list_automations(
    request: Request, enabled_only: bool = False
) -> Envelope[list[dict[str, Any]]]:
    """Permission not granted -> 400. Never a 404 -- an empty result is
    a normal, valid list."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_automations(enabled_only=enabled_only)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/home-automation/{trigger_id}", response_model=Envelope[dict[str, Any]])
async def get_automation(trigger_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Unknown automation -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).get_automation(trigger_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.post("/home-automation/{trigger_id}/enable", response_model=Envelope[dict[str, Any]])
async def enable_automation(trigger_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).enable_automation(trigger_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.post("/home-automation/{trigger_id}/disable", response_model=Envelope[dict[str, Any]])
async def disable_automation(trigger_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).disable_automation(trigger_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.delete("/home-automation/{trigger_id}", response_model=Envelope[dict[str, Any]])
async def delete_automation(trigger_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        deleted = await _service(request).delete_automation(trigger_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope({"automation_id": trigger_id, "deleted": deleted})


@router.post("/home-automation/{trigger_id}/run", response_model=Envelope[dict[str, Any]])
async def run_automation(trigger_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Manual test execution -- reuses the identical dispatch path an
    event-triggered match uses (Logic Contract §20/§21). Does not
    bypass action-level permission/confirmation. Unknown automation ->
    404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).run_automation(trigger_id)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(result)


@router.get(
    "/home-automation/{trigger_id}/executions", response_model=Envelope[list[dict[str, Any]]]
)
async def list_executions(
    trigger_id: str, request: Request, limit: int = 50
) -> Envelope[list[dict[str, Any]]]:
    """Unknown automation -> 404. Permission not granted -> 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _service(request).list_executions(trigger_id, limit=limit)
    except ServiceError as err:
        raise _handle(err) from err
    return envelope(rows, meta={"count": len(rows)})
