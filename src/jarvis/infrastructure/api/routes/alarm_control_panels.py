"""Alarm Control Panels API -- Milestone 12 Security & Safety
(alarm_control_panel Integration Slice).

``/api/v1/alarm-control-panels/*`` -- thin REST over
``AlarmControlPanelService``, the same ``{data, meta}`` envelope and
``Depends(get_current_session)`` Bearer auth every resource router
since M9 Task Group E uses. Its own top-level resource, not nested
under ``/security/*`` -- ``AlarmControlPanelService`` is its own
sibling service, not a ``SecurityService`` extension (Logic Contract
§2), so its route follows the same top-level-resource convention
every other device-category service uses (``/sirens``, ``/switches``,
...).

**No request body on any mutation route, deliberately.** Unlike Task
Group T's ``set_fan_percentage``/``set_cover_position``, none of
``arm_home``/``arm_away``/``disarm`` carries a value -- and, critically,
none of them accepts a ``code``/``pin`` field of any kind (Logic
Contract §8). No Pydantic request model is defined for these routes at
all, since there is no field to carry.

**Status-code convention**, identical to ``routes/sirens.py``: plain
``GET .../{id}`` -> 404 on unknown/wrong-domain; every action endpoint
-> 400 on any ``ServiceError`` (unknown device, wrong domain,
permission not granted alike).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.alarm_control_panel_service import AlarmControlPanelService

router = APIRouter(tags=["alarm-control-panels"], dependencies=[Depends(get_current_session)])


def _alarm_control_panels(request: Request) -> AlarmControlPanelService:
    return cast(
        "AlarmControlPanelService", request.app.state.container.alarm_control_panel_service()
    )


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/alarm-control-panels", response_model=Envelope[list[dict[str, Any]]])
async def list_alarm_control_panels(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every alarm control panel -- see
    ``AlarmControlPanelService.list_alarm_control_panels`` for why this
    does not make a live connector read per panel. Call
    ``GET .../alarm-control-panels/{id}`` for one panel's live state."""
    rows = await _alarm_control_panels(request).list_alarm_control_panels(
        home_id=home_id, room_id=room_id
    )
    return envelope(rows, meta={"count": len(rows)})


@router.get("/alarm-control-panels/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_alarm_control_panel(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _alarm_control_panels(request).get_alarm_control_panel_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/alarm-control-panels/{device_id}/arm_home", response_model=Envelope[dict[str, Any]])
async def arm_home(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _alarm_control_panels(request).arm_home(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/alarm-control-panels/{device_id}/arm_away", response_model=Envelope[dict[str, Any]])
async def arm_away(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _alarm_control_panels(request).arm_away(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/alarm-control-panels/{device_id}/disarm", response_model=Envelope[dict[str, Any]])
async def disarm(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _alarm_control_panels(request).disarm(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
