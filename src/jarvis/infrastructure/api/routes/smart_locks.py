"""Smart Locks API -- Milestone 12 Smart Locks.

``/api/v1/smart-locks/*`` -- thin REST over ``SmartLockService``, the
same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. Every
value returned here is already a plain, JSON-ready dict built by the
service layer, same as ``routes/smart_lighting.py``.

**No ``/state`` body-driven endpoint.** A lock has exactly one binary
attribute -- unlike Smart Lighting's merged ``/state`` (which exists to
combine several changed attributes into one wire call), two explicit
action endpoints (``/lock``, ``/unlock``) are clearer and match
``docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`` §7 exactly.

**Status-code convention**, identical to ``routes/smart_lighting.py``:
plain ``GET .../{id}`` -> 404 on unknown/wrong-type; every action
endpoint -> 400 on any ``ServiceError`` (unknown device, wrong type,
permission not granted alike), the same ``pair_device`` precedent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.smart_lock_service import SmartLockService

router = APIRouter(tags=["smart-locks"], dependencies=[Depends(get_current_session)])


def _smart_lock(request: Request) -> SmartLockService:
    return cast("SmartLockService", request.app.state.container.smart_lock_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/smart-locks", response_model=Envelope[list[dict[str, Any]]])
async def list_locks(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every lock -- see ``SmartLockService.
    list_locks`` for why this does not make a live connector read per
    lock. Call ``GET .../smart-locks/{id}`` for one lock's live state."""
    rows = await _smart_lock(request).list_locks(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/smart-locks/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_lock(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _smart_lock(request).get_lock_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/smart-locks/{device_id}/lock", response_model=Envelope[dict[str, Any]])
async def lock_device(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _smart_lock(request).lock(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/smart-locks/{device_id}/unlock", response_model=Envelope[dict[str, Any]])
async def unlock_device(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _smart_lock(request).unlock(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
