"""Sirens API -- Milestone 12 Security & Safety (Siren Integration
Slice).

``/api/v1/sirens/*`` -- thin REST over ``SirenService``, the same
``{data, meta}`` envelope and ``Depends(get_current_session)`` Bearer
auth every resource router since M9 Task Group E uses. Its own
top-level resource, not nested under ``/security/*`` -- ``SirenService``
is its own sibling service, not a ``SecurityService`` extension (Logic
Contract §3), so its route follows the same top-level-resource
convention every other device-category service uses (``/smart-locks``,
``/switches``, ...), not Developer Tools Connectivity Health's own
different reasoning for nesting under an unrelated router.

**No ``/state`` body-driven endpoint.** A siren has exactly one binary
attribute -- unlike Smart Lighting's merged ``/state``, two explicit
action endpoints (``/turn_on``, ``/turn_off``) are clearer and match
``docs/M12_SECURITY_SIREN_INTEGRATION_LOGIC_CONTRACT.md`` §7/§11
exactly, mirroring ``routes/smart_locks.py``'s own ``/lock``/``/unlock``
precedent.

**Status-code convention**, identical to ``routes/smart_locks.py``:
plain ``GET .../{id}`` -> 404 on unknown/wrong-domain; every action
endpoint -> 400 on any ``ServiceError`` (unknown device, wrong domain,
permission not granted alike).

**Task Group W** -- ``POST .../turn_on`` gains an optional request
body (``tone``/``duration``/``volume_level``, all ``None`` by
default) -- the same HA ``siren.turn_on`` service, never a new
endpoint (Logic Contract §13). An absent or empty body continues to
produce the exact bare ``turn_on`` call this route has always made.
``turn_off`` is unchanged -- HA's own ``siren.turn_off`` takes no
parameters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.siren_service import SirenService

router = APIRouter(tags=["sirens"], dependencies=[Depends(get_current_session)])


class TurnSirenOnRequest(BaseModel):
    tone: str | None = None
    duration: int | None = None
    volume_level: float | None = None


def _siren(request: Request) -> SirenService:
    return cast("SirenService", request.app.state.container.siren_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/sirens", response_model=Envelope[list[dict[str, Any]]])
async def list_sirens(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every siren -- see ``SirenService.
    list_sirens`` for why this does not make a live connector read per
    siren. Call ``GET .../sirens/{id}`` for one siren's live state."""
    rows = await _siren(request).list_sirens(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/sirens/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_siren(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _siren(request).get_siren_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/sirens/{device_id}/turn_on", response_model=Envelope[dict[str, Any]])
async def turn_siren_on(
    device_id: str, request: Request, body: TurnSirenOnRequest | None = None
) -> Envelope[dict[str, Any]]:
    """A missing or empty body produces the exact bare ``turn_on``
    call this route has always made (Logic Contract §13/§22)."""
    from jarvis.core.exceptions import ServiceError

    payload = body or TurnSirenOnRequest()
    try:
        result = await _siren(request).turn_on(
            device_id,
            tone=payload.tone,
            duration=payload.duration,
            volume_level=payload.volume_level,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/sirens/{device_id}/turn_off", response_model=Envelope[dict[str, Any]])
async def turn_siren_off(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _siren(request).turn_off(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
