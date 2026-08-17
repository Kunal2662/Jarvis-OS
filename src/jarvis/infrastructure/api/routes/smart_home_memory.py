"""Smart Home Memory API -- Milestone 12 Smart Home Memory (Manual/
On-Demand Device Snapshot Slice + Device-Category Expansion Slice).

``/api/v1/smart-home/memory/snapshots`` -- thin REST over
``SmartHomeMemoryService``, the same ``{data, meta}`` envelope and
``Depends(get_current_session)`` Bearer auth every resource router
since M9 Task Group E uses.

**Four routes**, matching the Expansion Logic Contract's own smallest-
coherent-surface decision (§23): the original ``POST``/``GET`` pair
(create one snapshot, list snapshots) plus ``DELETE .../{memory_id}``
(single-snapshot deletion) and ``POST .../home/{home_id}`` (home-wide
snapshot). No generic memory ``DELETE``, no per-device-category route.

**Status-code convention, mirroring ``routes/security.py``'s own
exception-type dispatch**: ``SmartHomeMemoryPermissionError`` (a
``ServiceError`` subclass) -> 400; ``UnsupportedSnapshotCategoryError``
(also a ``ServiceError`` subclass, the device exists but its category
isn't supported) -> 400; ``SnapshotNotFoundError`` (delete only) -> 404;
any other ``ServiceError`` (an unknown device/home, from
``SmartHomeService.require_device``/``require_home``) -> 404. Home-wide
snapshot never returns a non-200 for partial/zero success -- the
response body's own counts carry the outcome, mirroring Panic/Vacation
Mode's own convention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.smart_home_memory_service import SmartHomeMemoryService

router = APIRouter(tags=["smart-home-memory"], dependencies=[Depends(get_current_session)])


class SnapshotDeviceRequest(BaseModel):
    device_id: str


def _service(request: Request) -> SmartHomeMemoryService:
    return cast("SmartHomeMemoryService", request.app.state.container.smart_home_memory_service())


@router.post("/smart-home/memory/snapshots", response_model=Envelope[dict[str, Any]])
async def create_snapshot(
    body: SnapshotDeviceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Captures one device's current normalized state into memory,
    once, because this call was made. Permission not granted -> 400.
    Unsupported device category -> 400. Unknown device -> 404."""
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.smart_home_memory_service import (
        SmartHomeMemoryPermissionError,
        UnsupportedSnapshotCategoryError,
    )

    try:
        result = await _service(request).snapshot_device(body.device_id)
    except SmartHomeMemoryPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except UnsupportedSnapshotCategoryError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"device_id": result["device_id"]})


@router.get("/smart-home/memory/snapshots", response_model=Envelope[list[dict[str, Any]]])
async def list_snapshots(
    request: Request, device_id: str | None = None, limit: int = 50
) -> Envelope[list[dict[str, Any]]]:
    """Previously-created snapshots, most-recent-first, optionally
    filtered by ``device_id``. Permission not granted -> 400. Never a
    404 -- an empty/filtered-to-nothing result is a normal, valid
    list."""
    from jarvis.services.smart_home_memory_service import SmartHomeMemoryPermissionError

    try:
        rows = await _service(request).list_snapshots(device_id=device_id, limit=limit)
    except SmartHomeMemoryPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return envelope(rows, meta={"count": len(rows)})


@router.delete("/smart-home/memory/snapshots/{memory_id}", response_model=Envelope[dict[str, Any]])
async def delete_snapshot(memory_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Deletes one snapshot by memory id. Permission not granted -> 400.
    Unknown id, an id belonging to a non-snapshot memory, or an
    already-deleted snapshot -> 404 (indistinguishable, deliberately --
    see ``SnapshotNotFoundError``)."""
    from jarvis.services.smart_home_memory_service import (
        SmartHomeMemoryPermissionError,
        SnapshotNotFoundError,
    )

    try:
        result = await _service(request).delete_snapshot(memory_id)
    except SmartHomeMemoryPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except SnapshotNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result)


@router.post("/smart-home/memory/snapshots/home/{home_id}", response_model=Envelope[dict[str, Any]])
async def snapshot_home(home_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Snapshots every supported-category device in *home_id* in one
    call; unsupported categories are skipped, per-device failures never
    abort the batch. Permission not granted -> 400. Unknown home -> 404.
    Always 200 otherwise -- the response body's own counts carry
    partial/zero-success outcomes, never the HTTP status."""
    from jarvis.core.exceptions import ServiceError
    from jarvis.services.smart_home_memory_service import SmartHomeMemoryPermissionError

    try:
        result = await _service(request).snapshot_home(home_id)
    except SmartHomeMemoryPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(result, meta={"succeeded_count": result["succeeded_count"]})
