"""Sensors API -- Milestone 12 Sensors.

``/api/v1/sensors/*`` -- thin REST over ``SensorService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses. Every value
returned here is already a plain, JSON-ready dict built by the service
layer, same as ``routes/smart_lighting.py``/``routes/smart_locks.py``.

**Only two routes.** ``/capabilities`` and ``/status`` were evaluated
(``docs/M12_SENSORS_LOGIC_CONTRACT.md`` §11) and folded into
``GET /{id}``: this module has exactly one capability and one state
shape, so separate routes would return slices of the same already-cheap
read rather than new information.

**No mutation route exists anywhere in this module.** Sensors are
read-only -- every route here is ``GET``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.sensor_service import SensorService

router = APIRouter(tags=["sensors"], dependencies=[Depends(get_current_session)])


def _sensors(request: Request) -> SensorService:
    return cast("SensorService", request.app.state.container.sensor_service())


@router.get("/sensors", response_model=Envelope[list[dict[str, Any]]])
async def list_sensors(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every sensor -- see ``SensorService.
    list_sensors`` for why this does not make a live connector read per
    sensor. Call ``GET .../sensors/{id}`` for one sensor's live state."""
    from jarvis.services.sensor_service import SensorPermissionError

    try:
        rows = await _sensors(request).list_sensors(home_id=home_id, room_id=room_id)
    except SensorPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/sensors/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_sensor(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """404 for an unknown/wrong-type device -- the plain single-resource
    ``GET`` convention every other M12 module uses. 400 specifically for
    an ungranted ``smart_home`` permission -- Sensors is the only module
    where a plain read can fail that way (see ``docs/
    M12_SENSORS_LOGIC_CONTRACT.md`` §14/§20), so this checks exception
    type rather than reusing the same 404 every other read-by-id route
    returns, which would misreport "access denied" as "does not exist".
    """
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.sensor_service import SensorPermissionError

    try:
        state = await _sensors(request).get_sensor_state(device_id)
    except SensorPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)
