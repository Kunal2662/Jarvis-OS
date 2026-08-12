"""Thermostats API -- Milestone 12 Appliance Control (Climate /
Thermostat Slice).

``/api/v1/thermostats/*`` -- thin REST over ``ThermostatService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. Every
value returned here is already a plain, JSON-ready dict built by the
service layer.

**A merged ``POST .../state``, not per-attribute verb endpoints.**
Follows ``routes/smart_lighting.py``'s own body-driven ``/state``
precedent rather than Locks'/Appliances' ``/lock``/``/on``/``/open``
verbs: those suit single-attribute binary devices and cannot express
"set temperature and mode together" as one intent.

**Status-code convention**, identical to ``routes/smart_lighting.py``:
plain ``GET .../{id}`` -> 404 on unknown/wrong-type; the action
endpoint -> 400 on any ``ServiceError`` (unknown device, wrong type,
invalid value, empty mutation, permission not granted alike).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.thermostat_service import ThermostatService

router = APIRouter(tags=["thermostats"], dependencies=[Depends(get_current_session)])


class SetThermostatStateRequest(BaseModel):
    """Both fields optional; at least one must be supplied. The service
    layer -- not this schema -- rejects the both-``None`` case, so REST
    and agent-tool callers get the identical error."""

    temperature: float | None = None
    hvac_mode: str | None = None


def _thermostats(request: Request) -> ThermostatService:
    return cast("ThermostatService", request.app.state.container.thermostat_service())


@router.get("/thermostats", response_model=Envelope[list[dict[str, Any]]])
async def list_thermostats(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every thermostat -- see
    ``ThermostatService.list_thermostats`` for why this does not make a
    live connector read per device. Call ``GET .../thermostats/{id}``
    for one thermostat's live state."""
    rows = await _thermostats(request).list_thermostats(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/thermostats/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_thermostat(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _thermostats(request).get_thermostat_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/thermostats/{device_id}/state", response_model=Envelope[dict[str, Any]])
async def set_thermostat_state(
    device_id: str, body: SetThermostatStateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _thermostats(request).set_thermostat_state(
            device_id, temperature=body.temperature, hvac_mode=body.hvac_mode
        )
    except ServiceError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(result, meta={"success": result["success"]})
