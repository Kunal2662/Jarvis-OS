"""Security & Safety API -- Milestone 12 Security & Safety (Read-Only
Alert/Status Slice + Manual/On-Demand Action Slice).

``/api/v1/security/status`` -- thin REST over ``SecurityService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses.

**One read route only.** A separate ``/alerts`` route was evaluated
(``docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md`` §10) and rejected --
``active_alerts`` is already a field of this one aggregate response, so
a second route would return a slice of an already-cheap read.

**No 404 case exists on the read route** -- unlike every other M12
``GET .../{id}`` route, this endpoint has no single-resource identity
to be "not found"; the only failure mode is permission
(``ServiceError`` -> 400).

**Two action routes, added by Task Group M** (``docs/
M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md``): ``POST .../panic-mode``
and ``POST .../vacation-mode``, both body-driven (``{"home_id": str}``,
required), both returning the Action Slice's own multi-device result
shape -- never a bare boolean. Unlike the read route, these *do* have a
404 case: an unknown ``home_id`` is "not found," not a permission
failure. Any valid trigger -- regardless of whether its own
``status`` field is ``SUCCESS``/``PARTIAL_SUCCESS``/``FAILED``/
``NO_TARGETS`` -- is HTTP 200; none of those outcomes is an HTTP error
(Action Slice Logic Contract §9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.security_service import SecurityService

router = APIRouter(tags=["security"], dependencies=[Depends(get_current_session)])


class TriggerActionRequest(BaseModel):
    """``home_id`` is required -- unlike the read route's optional
    filter, a bulk home-wide action must never silently target
    nothing because of a missing field (Action Slice Logic Contract
    §4)."""

    home_id: str


def _security(request: Request) -> SecurityService:
    return cast("SecurityService", request.app.state.container.security_service())


@router.get("/security/status", response_model=Envelope[dict[str, Any]])
async def get_security_status(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[dict[str, Any]]:
    """Aggregate hazard-alert/status-sensor/lock status. Any
    ``ServiceError`` -- this module's own ``SecurityPermissionError``,
    or a ``SensorPermissionError`` propagated from the nested
    ``SensorService`` call (``core:sensors`` not granted, independent
    of this route's own ``core:security`` grant) -- maps to 400."""
    from jarvis.core.exceptions import ServiceError

    try:
        status = await _security(request).get_security_status(home_id=home_id, room_id=room_id)
    except ServiceError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(status, meta={"overall_status": status["overall_status"]})


@router.post("/security/panic-mode", response_model=Envelope[dict[str, Any]])
async def trigger_panic_mode(
    body: TriggerActionRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Lock every lock and turn on every light in ``home_id``, once.
    Permission not granted -> 400. Unknown ``home_id`` -> 404. Every
    other outcome (including ``PARTIAL_SUCCESS``/``FAILED``/
    ``NO_TARGETS``) -> 200 with the result's own ``status`` field
    naming what happened. A nested permission denial inside
    ``SmartLockService``/``SmartLightingService`` never reaches here --
    it is already folded into a per-device failure entry by
    ``SecurityService`` itself (Action Slice Logic Contract §7)."""
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.security_service import SecurityPermissionError

    try:
        result = await _security(request).trigger_panic_mode(body.home_id)
    except SecurityPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"status": result["status"]})


@router.post("/security/vacation-mode", response_model=Envelope[dict[str, Any]])
async def trigger_vacation_mode(
    body: TriggerActionRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Lock every lock, turn off every light, and best-effort
    eco-adjust every capable thermostat in ``home_id``, once.
    Permission not granted -> 400. Unknown ``home_id`` -> 404. Every
    other outcome -> 200, identical status-reporting shape to
    ``trigger_panic_mode``."""
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.security_service import SecurityPermissionError

    try:
        result = await _security(request).trigger_vacation_mode(body.home_id)
    except SecurityPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"status": result["status"]})
