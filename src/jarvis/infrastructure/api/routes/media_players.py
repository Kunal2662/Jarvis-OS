"""Media Player API -- Milestone 12 Appliance Control (Media Player
Core Slice).

``/api/v1/appliances/media-players/*`` -- thin REST over
``MediaPlayerService``, the same ``{data, meta}`` envelope and
``Depends(get_current_session)`` Bearer auth every resource router
since M9 Task Group E uses. Under the existing ``/appliances`` prefix,
matching ``routes/appliances.py``'s/``routes/vacuums_humidifiers.py``'s
own convention -- these are architectural siblings of Fan/Cover/Vacuum/
Humidifier even though they live in their own service.

**Transport -- five verb-style endpoints**, matching Vacuum's
binary-command shape: independent actions, not attributes that
combine, so no merged ``/state`` body carries them.

**State -- one merged ``/state`` endpoint** for volume/mute/source,
matching Thermostat's/Humidifier's shape: these three combine into one
intent.

**Status-code convention**, identical to
``routes/vacuums_humidifiers.py``/``routes/thermostats.py``: plain
``GET .../{id}`` -> 404 on unknown/wrong-type; every action endpoint ->
400 on any ``ServiceError`` (unknown device, wrong type/domain,
permission not granted, empty mutation alike). Reads are ungated, so no
permission-driven 400-vs-404 split applies here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.media_player_service import MediaPlayerService

router = APIRouter(tags=["media-players"], dependencies=[Depends(get_current_session)])


class SetMediaPlayerStateRequest(BaseModel):
    """All fields optional; at least one must be supplied -- the
    service layer rejects the all-``None`` case, so REST and
    agent-tool callers get the identical error."""

    volume: float | None = None
    muted: bool | None = None
    source: str | None = None


def _service(request: Request) -> MediaPlayerService:
    return cast("MediaPlayerService", request.app.state.container.media_player_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


@router.get("/appliances/media-players", response_model=Envelope[list[dict[str, Any]]])
async def list_media_players(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every media player -- see
    ``MediaPlayerService.list_media_players`` for why this does not
    make a live connector read per device. Call
    ``GET .../media-players/{id}`` for one device's live state."""
    rows = await _service(request).list_media_players(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/appliances/media-players/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _service(request).get_media_player_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/appliances/media-players/{device_id}/play", response_model=Envelope[dict[str, Any]])
async def play_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).play(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/media-players/{device_id}/pause", response_model=Envelope[dict[str, Any]])
async def pause_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).pause(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/media-players/{device_id}/stop", response_model=Envelope[dict[str, Any]])
async def stop_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).stop(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/media-players/{device_id}/next", response_model=Envelope[dict[str, Any]])
async def next_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).next_track(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post(
    "/appliances/media-players/{device_id}/previous", response_model=Envelope[dict[str, Any]]
)
async def previous_media_player(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).previous_track(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


@router.post("/appliances/media-players/{device_id}/state", response_model=Envelope[dict[str, Any]])
async def set_media_player_state(
    device_id: str, body: SetMediaPlayerStateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _service(request).set_media_player_state(
            device_id, volume=body.volume, muted=body.muted, source=body.source
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})
