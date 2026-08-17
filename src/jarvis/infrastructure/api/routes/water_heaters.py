"""Water Heater API -- Milestone 12 Appliance Control (Water Heater
Core Slice).

``/api/v1/appliances/water-heaters/*`` -- thin REST over
``WaterHeaterService``, the same ``{data, meta}`` envelope and
``Depends(get_current_session)`` Bearer auth every resource router
since M9 Task Group E uses. Under the existing ``/appliances`` prefix,
matching ``routes/thermostats.py``'s/``routes/media_players.py``'s own
convention -- an architectural sibling of Fan/Cover/Climate/Vacuum/
Humidifier/Media Player even though it lives in its own service.

**One merged ``/state`` endpoint, not verb endpoints.** Water heater
control has no independent zero-payload transport action (unlike
Vacuum/Media Player's transport half) -- every command here is an
attribute mutation, matching ``routes/thermostats.py``'s own merged
``/state`` shape exactly.

**Status-code convention**, identical to ``routes/thermostats.py``:
plain ``GET .../{id}`` -> 404 on unknown/wrong-type; the action
endpoint -> 400 on any ``ServiceError`` (unknown device, wrong type/
domain, invalid value, empty mutation, permission not granted alike).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.water_heater_service import WaterHeaterService

router = APIRouter(tags=["water-heaters"], dependencies=[Depends(get_current_session)])


class SetWaterHeaterStateRequest(BaseModel):
    """All fields optional; at least one must be supplied -- the
    service layer rejects the all-``None`` case, so REST and
    agent-tool callers get the identical error."""

    temperature: float | None = None
    operation_mode: str | None = None
    on: bool | None = None


def _service(request: Request) -> WaterHeaterService:
    return cast("WaterHeaterService", request.app.state.container.water_heater_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/appliances/water-heaters", response_model=Envelope[list[dict[str, Any]]])
async def list_water_heaters(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every water heater -- see
    ``WaterHeaterService.list_water_heaters`` for why this does not
    make a live connector read per device. Call
    ``GET .../water-heaters/{id}`` for one device's live state."""
    rows = await _service(request).list_water_heaters(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/water-heaters/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_water_heater(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _service(request).get_water_heater_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/water-heaters/{device_id}/state", response_model=Envelope[dict[str, Any]])
async def set_water_heater_state(
    device_id: str, body: SetWaterHeaterStateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).set_water_heater_state(
            device_id,
            temperature=body.temperature,
            operation_mode=body.operation_mode,
            on=body.on,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
