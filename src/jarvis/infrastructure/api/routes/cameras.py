"""Cameras API -- Milestone 12 Smart Cameras (Core Camera Slice).

``/api/v1/cameras/*`` -- thin REST over ``CameraService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses.

**Reads are gated here, unlike Lock/Switch/Appliance/Thermostat --
mirroring ``routes/sensors.py`` instead.** ``CameraService`` requires
the ``smart_home`` grant for every operation, including ``GET``, so a
plain single-resource read can fail two different ways: 400 for an
ungranted permission (checked by ``CameraPermissionError``'s distinct
exception type, not by sniffing the message string), 404 for an
unknown/wrong-type device -- the identical split ``routes/sensors.py``
already established.

**No merged ``/state`` endpoint.** A camera's four commands are
independent verbs, not attributes that combine -- four explicit action
endpoints mirror ``routes/smart_locks.py``'s own two-endpoint shape,
extended to four.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.camera_service import CameraService

router = APIRouter(tags=["cameras"], dependencies=[Depends(get_current_session)])


def _cameras(request: Request) -> CameraService:
    return cast("CameraService", request.app.state.container.camera_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/cameras", response_model=Envelope[list[dict[str, Any]]])
async def list_cameras(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every camera -- see ``CameraService.
    list_cameras`` for why this does not make a live connector read per
    camera. Call ``GET .../cameras/{id}`` for one camera's live state."""
    from jarvis.services.camera_service import CameraPermissionError

    try:
        rows = await _cameras(request).list_cameras(home_id=home_id, room_id=room_id)
    except CameraPermissionError as err:
        raise _bad_request(err) from err
    return envelope(rows, meta={"count": len(rows)})


@router.get("/cameras/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_camera(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.camera_service import CameraPermissionError

    try:
        state = await _cameras(request).get_camera_state(device_id)
    except CameraPermissionError as err:
        raise _bad_request(err) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/cameras/{device_id}/turn_on", response_model=Envelope[dict[str, Any]])
async def turn_camera_on(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _cameras(request).turn_on(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/cameras/{device_id}/turn_off", response_model=Envelope[dict[str, Any]])
async def turn_camera_off(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _cameras(request).turn_off(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post(
    "/cameras/{device_id}/enable_motion_detection", response_model=Envelope[dict[str, Any]]
)
async def enable_camera_motion_detection(
    device_id: str, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _cameras(request).enable_motion_detection(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post(
    "/cameras/{device_id}/disable_motion_detection", response_model=Envelope[dict[str, Any]]
)
async def disable_camera_motion_detection(
    device_id: str, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _cameras(request).disable_motion_detection(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
