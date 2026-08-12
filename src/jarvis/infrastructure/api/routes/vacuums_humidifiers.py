"""Vacuum + Humidifier API -- Milestone 12 Appliance Control (Vacuum +
Humidifier Core Slice).

``/api/v1/appliances/vacuums/*`` and
``/api/v1/appliances/humidifiers/*`` -- thin REST over
``VacuumHumidifierService``, the same ``{data, meta}`` envelope and
``Depends(get_current_session)`` Bearer auth every resource router
since M9 Task Group E uses. Under the existing ``/appliances`` prefix,
matching ``routes/appliances.py``'s own ``/appliances/fans``,
``/appliances/covers`` convention -- these are architectural siblings of
Fan/Cover even though they live in their own service (Logic Contract
§11).

**Vacuum -- verb-style endpoints**, matching Fan/Cover's binary-command
shape: four independent commands, not attributes that combine, so no
merged ``/state`` body exists for it.

**Humidifier -- one merged ``/state`` endpoint**, matching
``routes/thermostats.py``'s shape: on/off and target humidity combine
into one intent.

**Status-code convention**, identical to ``routes/smart_switches.py``/
``routes/thermostats.py``: plain ``GET .../{id}`` -> 404 on
unknown/wrong-type; every action endpoint -> 400 on any
``ServiceError`` (unknown device, wrong type/domain, permission not
granted, empty mutation alike). Reads are ungated, so no
permission-driven 400-vs-404 split applies here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.vacuum_humidifier_service import VacuumHumidifierService

router = APIRouter(tags=["vacuums-humidifiers"], dependencies=[Depends(get_current_session)])


class SetHumidifierStateRequest(BaseModel):
    """Both fields optional; at least one must be supplied -- the
    service layer rejects the both-``None`` case, so REST and
    agent-tool callers get the identical error."""

    on: bool | None = None
    target_humidity: float | None = None


def _service(request: Request) -> VacuumHumidifierService:
    return cast("VacuumHumidifierService", request.app.state.container.vacuum_humidifier_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Vacuums
# ---------------------------------------------------------------------------
@router.get("/appliances/vacuums", response_model=Envelope[list[dict[str, Any]]])
async def list_vacuums(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every vacuum -- see
    ``VacuumHumidifierService.list_vacuums`` for why this does not make
    a live connector read per vacuum. Call ``GET .../vacuums/{id}`` for
    one vacuum's live state."""
    rows = await _service(request).list_vacuums(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/vacuums/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_vacuum(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _service(request).get_vacuum_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/vacuums/{device_id}/start", response_model=Envelope[dict[str, Any]])
async def start_vacuum(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).start(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/vacuums/{device_id}/stop", response_model=Envelope[dict[str, Any]])
async def stop_vacuum(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).stop(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/vacuums/{device_id}/pause", response_model=Envelope[dict[str, Any]])
async def pause_vacuum(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).pause(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/vacuums/{device_id}/dock", response_model=Envelope[dict[str, Any]])
async def dock_vacuum(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Maps to ``return_to_base`` -- ``dock`` is the shorter, equally
    clear REST verb; the normalized command name itself stays
    ``RETURN_TO_BASE`` (Logic Contract §11)."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).return_to_base(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


# ---------------------------------------------------------------------------
# Humidifiers
# ---------------------------------------------------------------------------
@router.get("/appliances/humidifiers", response_model=Envelope[list[dict[str, Any]]])
async def list_humidifiers(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every humidifier -- see
    ``VacuumHumidifierService.list_humidifiers`` for why this does not
    make a live connector read per humidifier."""
    rows = await _service(request).list_humidifiers(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/humidifiers/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_humidifier(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _service(request).get_humidifier_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/humidifiers/{device_id}/state", response_model=Envelope[dict[str, Any]])
async def set_humidifier_state(
    device_id: str, body: SetHumidifierStateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).set_humidifier_state(
            device_id, on=body.on, target_humidity=body.target_humidity
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
