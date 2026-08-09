"""Smart Switches API -- Milestone 12 Energy Management (Core Energy
Slice).

``/api/v1/switches/*`` -- thin REST over ``SmartSwitchService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. Every
value returned here is already a plain, JSON-ready dict built by the
service layer, same as ``routes/smart_locks.py``.

**Reads are not permission-gated here** (unlike ``routes/sensors.py``)
-- a switch's on/off state carries no comparable privacy weight to
sensor data; see ``docs/M12_ENERGY_MANAGEMENT_LOGIC_CONTRACT.md`` §9.
So, unlike Sensors, a plain ``GET /switches/{id}`` has only one
``ServiceError`` cause (not found/wrong type) and maps to 404 exactly
like every other M12 module's single-resource ``GET``.

**No power/energy reading route exists here.** Those already exist
under ``routes/sensors.py`` -- see the Logic Contract §11.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.smart_switch_service import SmartSwitchService

router = APIRouter(tags=["smart-switches"], dependencies=[Depends(get_current_session)])


def _switches(request: Request) -> SmartSwitchService:
    return cast("SmartSwitchService", request.app.state.container.smart_switch_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/switches", response_model=Envelope[list[dict[str, Any]]])
async def list_switches(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every switch -- see ``SmartSwitchService
    .list_switches`` for why this does not make a live connector read
    per switch. Call ``GET .../switches/{id}`` for one switch's live
    state."""
    rows = await _switches(request).list_switches(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/switches/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_switch(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _switches(request).get_switch_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/switches/{device_id}/on", response_model=Envelope[dict[str, Any]])
async def turn_switch_on(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _switches(request).turn_on(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/switches/{device_id}/off", response_model=Envelope[dict[str, Any]])
async def turn_switch_off(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _switches(request).turn_off(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
