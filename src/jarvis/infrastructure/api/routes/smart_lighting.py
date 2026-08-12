"""Smart Lighting API -- Milestone 12 Connectivity REST + Smart Lighting.

``/api/v1/smart-lighting/*`` -- thin REST over ``SmartLightingService``,
the same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. Every
value returned here is already a plain, JSON-ready dict built by the
service layer -- unlike ``routes/smart_home.py``, this router has no
payload builders of its own.

**Status-code convention.** A plain ``GET .../lights/{id}`` follows
every other single-resource ``GET`` in this codebase: unknown id -> 404.
Every action endpoint (state changes, scene apply/delete) follows
``routes/smart_home.py``'s own ``pair_device`` precedent instead: the
service raises the same ``ServiceError`` for "device not found",
"invalid attribute value" and "permission not granted" alike, and this
router maps all three to 400 rather than sniffing the message to guess
which -- the same simplifying choice ``pair_device`` already made for
an action route in this exact domain.

**No parallel execution path.** Every method here calls the same
``SmartLightingService`` the agent tools (``agents/tools/
smart_lighting_tools.py``) call -- both converge on
``ConnectivityService.send_command``, and both trip the same
``smart_home`` permission check. See ``services/smart_lighting_service.
py``'s own module docstring for the permission model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.smart_lighting_service import SmartLightingService

router = APIRouter(tags=["smart-lighting"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class SetLightStateRequest(BaseModel):
    on: bool | None = None
    brightness: int | None = None
    color_temp_kelvin: int | None = None
    color: tuple[int, int, int] | None = None


class CreateSceneRequest(BaseModel):
    home_id: str
    name: str
    targets: list[dict[str, Any]]


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------
def _smart_lighting(request: Request) -> SmartLightingService:
    return cast("SmartLightingService", request.app.state.container.smart_lighting_service())


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Lights
# ---------------------------------------------------------------------------
@router.get("/smart-lighting/lights", response_model=Envelope[list[dict[str, Any]]])
async def list_lights(
    request: Request, home_id: str | None = None, room_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    """Last-known DB state for every light -- see ``SmartLightingService
    .list_lights`` for why this does not make a live connector read per
    light. Call ``GET .../lights/{id}`` for one light's live state."""
    rows = await _smart_lighting(request).list_lights(home_id=home_id, room_id=room_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/smart-lighting/lights/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_light(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        state = await _smart_lighting(request).get_light_state(device_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(state)


@router.post("/smart-lighting/lights/{device_id}/state", response_model=Envelope[dict[str, Any]])
async def set_light_state(
    device_id: str, body: SetLightStateRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _smart_lighting(request).set_light_state(
            device_id,
            on=body.on,
            brightness=body.brightness,
            color_temp_kelvin=body.color_temp_kelvin,
            color=body.color,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(result, meta={"success": result["success"]})


# ---------------------------------------------------------------------------
# Room / group fan-out
# ---------------------------------------------------------------------------
@router.post("/smart-lighting/rooms/{room_id}/state", response_model=Envelope[list[dict[str, Any]]])
async def set_room_state(
    room_id: str, body: SetLightStateRequest, request: Request
) -> Envelope[list[dict[str, Any]]]:
    """Applies to every light in the room -- an unknown or empty room
    returns an empty list, matching ``SmartHomeService.list_devices``'s
    own no-existence-check behavior for a room filter."""
    from jarvis.core.exceptions import ServiceError

    try:
        results = await _smart_lighting(request).apply_room(
            room_id,
            on=body.on,
            brightness=body.brightness,
            color_temp_kelvin=body.color_temp_kelvin,
            color=body.color,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    ok = sum(1 for r in results if r["success"])
    return envelope(results, meta={"count": len(results), "succeeded": ok})


@router.post(
    "/smart-lighting/groups/{group_id}/state", response_model=Envelope[list[dict[str, Any]]]
)
async def set_group_state(
    group_id: str, body: SetLightStateRequest, request: Request
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        results = await _smart_lighting(request).apply_group(
            group_id,
            on=body.on,
            brightness=body.brightness,
            color_temp_kelvin=body.color_temp_kelvin,
            color=body.color,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    ok = sum(1 for r in results if r["success"])
    return envelope(results, meta={"count": len(results), "succeeded": ok})


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------
@router.post("/smart-lighting/scenes", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_scene(body: CreateSceneRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        scene = await _smart_lighting(request).create_scene(body.home_id, body.name, body.targets)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(scene, meta={"created": True})


@router.get("/smart-lighting/scenes", response_model=Envelope[list[dict[str, Any]]])
async def list_scenes(
    request: Request, home_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    rows = await _smart_lighting(request).list_scenes(home_id=home_id)
    return envelope(rows, meta={"count": len(rows)})


@router.get("/smart-lighting/scenes/{scene_id}", response_model=Envelope[dict[str, Any]])
async def get_scene(scene_id: str, request: Request) -> Envelope[dict[str, Any]]:
    scene = await _smart_lighting(request).get_scene(scene_id)
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found.")
    return envelope(scene)


@router.delete("/smart-lighting/scenes/{scene_id}", status_code=204)
async def delete_scene(scene_id: str, request: Request) -> None:
    from jarvis.core.exceptions import ServiceError

    try:
        deleted = await _smart_lighting(request).delete_scene(scene_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail="Scene not found.")


@router.post(
    "/smart-lighting/scenes/{scene_id}/apply", response_model=Envelope[list[dict[str, Any]]]
)
async def apply_scene(scene_id: str, request: Request) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        results = await _smart_lighting(request).apply_scene(scene_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    ok = sum(1 for r in results if r["success"])
    return envelope(results, meta={"count": len(results), "succeeded": ok})
