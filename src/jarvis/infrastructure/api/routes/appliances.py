"""Appliance Control API -- Milestone 12 Appliance Control (Core
Appliance Slice: Fans + Covers).

``/api/v1/appliances/*`` -- thin REST over ``ApplianceService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. Every
value returned here is already a plain, JSON-ready dict built by the
service layer, same as ``routes/smart_switches.py``.

**Two sibling resource collections, not one generic ``/appliances/{id}/
command`` endpoint.** A fan and a cover have genuinely different
command vocabularies (``on``/``off`` vs ``open``/``close``) -- see
``docs/M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.md`` §12.

**Reads are not permission-gated here** (unlike ``routes/sensors.py``)
-- fan/cover state carries no comparable privacy weight to sensor data;
see the Logic Contract §14. So, unlike Sensors, a plain ``GET`` has only
one ``ServiceError`` cause (not found/wrong type/wrong domain) and maps
to 404 exactly like every other M12 module's single-resource ``GET``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.appliance_service import ApplianceService

router = APIRouter(tags=["appliances"], dependencies=[Depends(get_current_session)])


def _appliances(request: Request) -> ApplianceService:
    return cast("ApplianceService", request.app.state.container.appliance_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


# ------------------------------------------------------------------
# Fans
# ------------------------------------------------------------------
@router.get("/appliances/fans", response_model=Envelope[list[dict[str, Any]]])
async def list_fans(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every fan -- see ``ApplianceService.
    list_fans`` for why this does not make a live connector read per
    fan. Call ``GET .../fans/{id}`` for one fan's live state."""
    rows = await _appliances(request).list_fans(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/fans/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_fan(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _appliances(request).get_fan_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/fans/{device_id}/on", response_model=Envelope[dict[str, Any]])
async def turn_fan_on(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _appliances(request).fan_on(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/fans/{device_id}/off", response_model=Envelope[dict[str, Any]])
async def turn_fan_off(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _appliances(request).fan_off(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


# ------------------------------------------------------------------
# Covers
# ------------------------------------------------------------------
@router.get("/appliances/covers", response_model=Envelope[list[dict[str, Any]]])
async def list_covers(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every cover -- see ``ApplianceService.
    list_covers`` for why this does not make a live connector read per
    cover. Call ``GET .../covers/{id}`` for one cover's live state."""
    rows = await _appliances(request).list_covers(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/covers/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_cover(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _appliances(request).get_cover_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/covers/{device_id}/open", response_model=Envelope[dict[str, Any]])
async def open_cover(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _appliances(request).cover_open(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/covers/{device_id}/close", response_model=Envelope[dict[str, Any]])
async def close_cover(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _appliances(request).cover_close(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
