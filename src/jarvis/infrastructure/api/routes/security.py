"""Security & Safety API -- Milestone 12 Security & Safety (Read-Only
Alert/Status Slice).

``/api/v1/security/status`` -- thin REST over ``SecurityService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses.

**One route only.** A separate ``/alerts`` route was evaluated
(``docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md`` §10) and rejected --
``active_alerts`` is already a field of this one aggregate response, so
a second route would return a slice of an already-cheap read.

**No mutation route exists anywhere in this module.** This is
informational only -- see the Logic Contract §17.

**No 404 case exists here** -- unlike every other M12 ``GET .../{id}``
route, this endpoint has no single-resource identity to be "not found";
the only failure mode is permission (``ServiceError`` -> 400).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.security_service import SecurityService

router = APIRouter(tags=["security"], dependencies=[Depends(get_current_session)])


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
