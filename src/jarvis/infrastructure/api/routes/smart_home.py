"""Smart Home API -- Milestone 12 Task Group A (Smart Home Core).

``/api/v1/homes``, ``/api/v1/smart-home/zones``,
``/api/v1/smart-home/rooms``, ``/api/v1/devices`` and
``/api/v1/smart-home/device-groups`` -- thin REST over
``SmartHomeService``. Same ``Depends(get_current_session)`` Bearer auth
and ``{data, meta}`` envelope every resource router since M9 Task Group
E uses; this one owns no state and no logic of its own.

**Devices and homes get short, top-level prefixes** (``/devices``,
``/homes``) because they are the two things a client fetches on their
own most often -- a device list for a dashboard, a home for a picker.
Zones/rooms/device-groups are nested under ``/smart-home/`` rather than
given the same top-level treatment, matching how M11's own router drew
the line between "addressable on its own" (notes) and "always read in
context" -- unlike M11, though, this is a naming choice made once at
this task group's start rather than a lesson learned from a shipped
API, since nothing here has a caller yet to disrupt.

**Discovery and pairing are not full endpoints of their own.** Device
Discovery/Pairing (Smart Home Core's own module items) are represented
by ``POST /devices`` (register a discovery result -- ``status`` starts
at ``"discovered"``) and ``POST /devices/{id}/pair``. Neither talks to
real hardware; see ``services/smart_home_service.py``'s own docstring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session
from jarvis.infrastructure.api.pagination import Page, page_meta, page_params

if TYPE_CHECKING:
    from jarvis.services.smart_home_service import SmartHomeService

router = APIRouter(tags=["smart-home"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class CreateHomeRequest(BaseModel):
    name: str
    description: str = ""


class UpdateHomeRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class CreateZoneRequest(BaseModel):
    home_id: str
    name: str
    description: str = ""


class UpdateZoneRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class CreateRoomRequest(BaseModel):
    home_id: str
    name: str
    description: str = ""
    zone_id: str | None = None


class UpdateRoomRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    zone_id: str | None = None
    clear_zone: bool = False


class RegisterDeviceRequest(BaseModel):
    home_id: str
    name: str
    device_type: str = "other"
    room_id: str | None = None
    manufacturer: str = ""
    model: str = ""
    external_id: str | None = None


class UpdateDeviceRequest(BaseModel):
    name: str | None = None
    device_type: str | None = None
    room_id: str | None = None
    clear_room: bool = False
    manufacturer: str | None = None
    model: str | None = None


class CreateDeviceGroupRequest(BaseModel):
    home_id: str
    name: str
    description: str = ""


class DeviceGroupMemberRequest(BaseModel):
    device_id: str


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _smart_home(request: Request) -> SmartHomeService:
    return cast("SmartHomeService", request.app.state.container.smart_home_service())


def _home_payload(home: Any) -> dict[str, Any]:
    return {
        "id": home.id,
        "name": home.name,
        "description": home.description,
        "status": home.status,
        "created_at": home.created_at.isoformat() if home.created_at else None,
        "updated_at": home.updated_at.isoformat() if home.updated_at else None,
    }


def _zone_payload(zone: Any) -> dict[str, Any]:
    return {
        "id": zone.id,
        "home_id": zone.home_id,
        "name": zone.name,
        "description": zone.description,
        "created_at": zone.created_at.isoformat() if zone.created_at else None,
        "updated_at": zone.updated_at.isoformat() if zone.updated_at else None,
    }


def _room_payload(room: Any) -> dict[str, Any]:
    return {
        "id": room.id,
        "home_id": room.home_id,
        "zone_id": room.zone_id,
        "name": room.name,
        "description": room.description,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "updated_at": room.updated_at.isoformat() if room.updated_at else None,
    }


def _device_payload(device: Any) -> dict[str, Any]:
    return {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "device_type": device.device_type,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }


def _device_group_payload(group: Any) -> dict[str, Any]:
    return {
        "id": group.id,
        "home_id": group.home_id,
        "name": group.name,
        "description": group.description,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "updated_at": group.updated_at.isoformat() if group.updated_at else None,
    }


def _bad_request(err: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Homes
# ---------------------------------------------------------------------------
@router.post("/homes", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_home(body: CreateHomeRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        home = await _smart_home(request).create_home(body.name, description=body.description)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_home_payload(home), meta={"created": True})


@router.get("/homes", response_model=Envelope[list[dict[str, Any]]])
async def list_homes(
    request: Request, status: str | None = None, page: Page = Depends(page_params)
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _smart_home(request).list_homes(
            status=status, limit=page.probe_limit, offset=page.offset
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    rows, has_more = page.trim(rows)
    payload = [_home_payload(h) for h in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/homes/{home_id}", response_model=Envelope[dict[str, Any]])
async def get_home(home_id: str, request: Request) -> Envelope[dict[str, Any]]:
    home = await _smart_home(request).get_home(home_id)
    if home is None:
        raise HTTPException(status_code=404, detail="Home not found.")
    return envelope(_home_payload(home))


@router.get("/homes/{home_id}/metadata", response_model=Envelope[dict[str, Any]])
async def home_metadata(home_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Derived device/room/zone counts -- Device Health Monitoring and
    the Device Status Dashboard's own data source."""
    from jarvis.core.exceptions import ServiceError

    try:
        metadata = await _smart_home(request).metadata(home_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(metadata.as_dict())


@router.patch("/homes/{home_id}", response_model=Envelope[dict[str, Any]])
async def update_home(
    home_id: str, body: UpdateHomeRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        home = await _smart_home(request).update_home(
            home_id, name=body.name, description=body.description, status=body.status
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if home is None:
        raise HTTPException(status_code=404, detail="Home not found.")
    return envelope(_home_payload(home))


@router.delete("/homes/{home_id}", status_code=204)
async def delete_home(home_id: str, request: Request) -> None:
    if not await _smart_home(request).delete_home(home_id):
        raise HTTPException(status_code=404, detail="Home not found.")


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------
@router.post("/smart-home/zones", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_zone(body: CreateZoneRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        zone = await _smart_home(request).create_zone(
            body.home_id, body.name, description=body.description
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_zone_payload(zone), meta={"created": True})


@router.get("/smart-home/zones", response_model=Envelope[list[dict[str, Any]]])
async def list_zones(
    request: Request, home_id: str | None = None, page: Page = Depends(page_params)
) -> Envelope[list[dict[str, Any]]]:
    rows = await _smart_home(request).list_zones(
        home_id=home_id, limit=page.probe_limit, offset=page.offset
    )
    rows, has_more = page.trim(rows)
    payload = [_zone_payload(z) for z in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/smart-home/zones/{zone_id}", response_model=Envelope[dict[str, Any]])
async def get_zone(zone_id: str, request: Request) -> Envelope[dict[str, Any]]:
    zone = await _smart_home(request).get_zone(zone_id)
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return envelope(_zone_payload(zone))


@router.patch("/smart-home/zones/{zone_id}", response_model=Envelope[dict[str, Any]])
async def update_zone(
    zone_id: str, body: UpdateZoneRequest, request: Request
) -> Envelope[dict[str, Any]]:
    zone = await _smart_home(request).update_zone(
        zone_id, name=body.name, description=body.description
    )
    if zone is None:
        raise HTTPException(status_code=404, detail="Zone not found.")
    return envelope(_zone_payload(zone))


@router.delete("/smart-home/zones/{zone_id}", status_code=204)
async def delete_zone(zone_id: str, request: Request) -> None:
    """Deletes the zone; its rooms are unassigned, not deleted -- see
    ``SmartHomeService.delete_zone``."""
    if not await _smart_home(request).delete_zone(zone_id):
        raise HTTPException(status_code=404, detail="Zone not found.")


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
@router.post("/smart-home/rooms", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_room(body: CreateRoomRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        room = await _smart_home(request).create_room(
            body.home_id, body.name, description=body.description, zone_id=body.zone_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_room_payload(room), meta={"created": True})


@router.get("/smart-home/rooms", response_model=Envelope[list[dict[str, Any]]])
async def list_rooms(
    request: Request,
    home_id: str | None = None,
    zone_id: str | None = None,
    page: Page = Depends(page_params),
) -> Envelope[list[dict[str, Any]]]:
    rows = await _smart_home(request).list_rooms(
        home_id=home_id, zone_id=zone_id, limit=page.probe_limit, offset=page.offset
    )
    rows, has_more = page.trim(rows)
    payload = [_room_payload(r) for r in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/smart-home/rooms/{room_id}", response_model=Envelope[dict[str, Any]])
async def get_room(room_id: str, request: Request) -> Envelope[dict[str, Any]]:
    room = await _smart_home(request).get_room(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    return envelope(_room_payload(room))


@router.patch("/smart-home/rooms/{room_id}", response_model=Envelope[dict[str, Any]])
async def update_room(
    room_id: str, body: UpdateRoomRequest, request: Request
) -> Envelope[dict[str, Any]]:
    room = await _smart_home(request).update_room(
        room_id,
        name=body.name,
        description=body.description,
        zone_id=body.zone_id,
        clear_zone=body.clear_zone,
    )
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    return envelope(_room_payload(room))


@router.delete("/smart-home/rooms/{room_id}", status_code=204)
async def delete_room(room_id: str, request: Request) -> None:
    """Deletes the room; its devices are unassigned, not deleted -- see
    ``SmartHomeService.delete_room``."""
    if not await _smart_home(request).delete_room(room_id):
        raise HTTPException(status_code=404, detail="Room not found.")


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
@router.post("/devices", response_model=Envelope[dict[str, Any]], status_code=201)
async def register_device(
    body: RegisterDeviceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Records a discovery result -- see this module's own docstring
    for why this is how Device Discovery is represented in this task
    group."""
    from jarvis.core.exceptions import ServiceError

    try:
        device = await _smart_home(request).register_discovered_device(
            body.home_id,
            body.name,
            device_type=body.device_type,
            room_id=body.room_id,
            manufacturer=body.manufacturer,
            model=body.model,
            external_id=body.external_id,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_device_payload(device), meta={"created": True})


@router.get("/devices", response_model=Envelope[list[dict[str, Any]]])
async def list_devices(
    request: Request,
    *,
    home_id: str | None = None,
    room_id: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    page: Page = Depends(page_params),
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        rows = await _smart_home(request).list_devices(
            home_id=home_id,
            room_id=room_id,
            device_type=device_type,
            status=status,
            limit=page.probe_limit,
            offset=page.offset,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    rows, has_more = page.trim(rows)
    payload = [_device_payload(d) for d in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/devices/{device_id}", response_model=Envelope[dict[str, Any]])
async def get_device(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    device = await _smart_home(request).get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    return envelope(_device_payload(device))


@router.post("/devices/{device_id}/pair", response_model=Envelope[dict[str, Any]])
async def pair_device(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Transitions a discovered (or offline/unreachable) device to
    ``paired`` -- see ``SmartHomeService.pair_device`` for why there is
    no real handshake behind this yet."""
    from jarvis.core.exceptions import ServiceError

    try:
        device = await _smart_home(request).pair_device(device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    return envelope(_device_payload(device))


@router.patch("/devices/{device_id}", response_model=Envelope[dict[str, Any]])
async def update_device(
    device_id: str, body: UpdateDeviceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        device = await _smart_home(request).update_device(
            device_id,
            name=body.name,
            device_type=body.device_type,
            room_id=body.room_id,
            clear_room=body.clear_room,
            manufacturer=body.manufacturer,
            model=body.model,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found.")
    return envelope(_device_payload(device))


@router.delete("/devices/{device_id}", status_code=204)
async def delete_device(device_id: str, request: Request) -> None:
    if not await _smart_home(request).delete_device(device_id):
        raise HTTPException(status_code=404, detail="Device not found.")


# ---------------------------------------------------------------------------
# Device groups
# ---------------------------------------------------------------------------
@router.post("/smart-home/device-groups", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_device_group(
    body: CreateDeviceGroupRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        group = await _smart_home(request).create_device_group(
            body.home_id, body.name, description=body.description
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_device_group_payload(group), meta={"created": True})


@router.get("/smart-home/device-groups", response_model=Envelope[list[dict[str, Any]]])
async def list_device_groups(
    request: Request, home_id: str | None = None, page: Page = Depends(page_params)
) -> Envelope[list[dict[str, Any]]]:
    rows = await _smart_home(request).list_device_groups(
        home_id=home_id, limit=page.probe_limit, offset=page.offset
    )
    rows, has_more = page.trim(rows)
    payload = [_device_group_payload(g) for g in rows]
    return envelope(payload, meta=page_meta(page=page, count=len(payload), has_more=has_more))


@router.get("/smart-home/device-groups/{group_id}", response_model=Envelope[dict[str, Any]])
async def get_device_group(group_id: str, request: Request) -> Envelope[dict[str, Any]]:
    group = await _smart_home(request).get_device_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Device group not found.")
    return envelope(_device_group_payload(group))


@router.delete("/smart-home/device-groups/{group_id}", status_code=204)
async def delete_device_group(group_id: str, request: Request) -> None:
    if not await _smart_home(request).delete_device_group(group_id):
        raise HTTPException(status_code=404, detail="Device group not found.")


@router.get(
    "/smart-home/device-groups/{group_id}/members",
    response_model=Envelope[list[dict[str, Any]]],
)
async def list_device_group_members(
    group_id: str, request: Request
) -> Envelope[list[dict[str, Any]]]:
    group = await _smart_home(request).get_device_group(group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Device group not found.")
    members = await _smart_home(request).list_group_members(group_id)
    return envelope([_device_payload(d) for d in members])


@router.post(
    "/smart-home/device-groups/{group_id}/members",
    response_model=Envelope[dict[str, Any]],
    status_code=201,
)
async def add_device_group_member(
    group_id: str, body: DeviceGroupMemberRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        added = await _smart_home(request).add_device_to_group(group_id, body.device_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope({"group_id": group_id, "device_id": body.device_id}, meta={"added": added})


@router.delete("/smart-home/device-groups/{group_id}/members/{device_id}", status_code=204)
async def remove_device_group_member(group_id: str, device_id: str, request: Request) -> None:
    if not await _smart_home(request).remove_device_from_group(group_id, device_id):
        raise HTTPException(status_code=404, detail="Membership not found.")
