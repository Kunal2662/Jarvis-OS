"""Connectivity API -- Milestone 12 Connectivity REST + Smart Lighting.

``/api/v1/connectivity/*`` -- thin REST over ``ConnectivityService``,
the same ``{data, meta}`` envelope and ``Depends(get_current_session)``
Bearer auth every resource router since M9 Task Group E uses. This
router owns no state and no logic of its own; it does not expose
anything ``ConnectivityService`` cannot already do (no vendor-transport
selection, no credential handling beyond the connector's own *config*
dict, no functionality invented on top of the five ``IDeviceConnector``
methods).

**Generic, protocol-agnostic commands only.** ``POST .../devices/{id}/
command`` passes *command*/*payload* straight through to
``ConnectivityService.send_command`` -- exactly as uninterpreted here as
it is there. Smart Lighting's own normalized operations
(``routes/smart_lighting.py``) are a separate, higher-level router built
on top of this same service; this router is not where command
translation happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.core.interfaces.connectivity import CONNECTOR_TYPES, ConnectivityError
from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

router = APIRouter(tags=["connectivity"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class ConnectRequest(BaseModel):
    config: dict[str, Any] = {}


class DiscoverRequest(BaseModel):
    connector_type: str
    home_id: str


class SendCommandRequest(BaseModel):
    command: str
    payload: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _connectivity(request: Request) -> ConnectivityService:
    return cast("ConnectivityService", request.app.state.container.connectivity_service())


def _smart_home(request: Request) -> SmartHomeService:
    return cast("SmartHomeService", request.app.state.container.smart_home_service())


def _device_payload(device: Any) -> dict[str, Any]:
    return {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "device_type": device.device_type,
        "status": device.status,
        "external_id": device.external_id,
        "last_seen_at": device.last_seen_at.isoformat() if device.last_seen_at else None,
    }


def _connectivity_error(err: Exception) -> HTTPException:
    """A ``ConnectivityError`` (unregistered connector type, connector
    unreachable, not connected) is a real, expected outcome -- the
    connector or its configuration, never this router's own logic. 400,
    matching ``_bad_request``'s reasoning in every other resource
    router."""
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Connector lifecycle
# ---------------------------------------------------------------------------
@router.get("/connectivity/connectors", response_model=Envelope[list[dict[str, Any]]])
async def list_connectors(request: Request) -> Envelope[list[dict[str, Any]]]:
    """Every connector type this build recognizes (``CONNECTOR_TYPES``),
    each with its live connected status -- data only, never a vendor
    request."""
    service = _connectivity(request)
    rows = [
        {"connector_type": t, "connected": service.is_connected(t)} for t in sorted(CONNECTOR_TYPES)
    ]
    return envelope(rows, meta={"count": len(rows)})


@router.post(
    "/connectivity/connectors/{connector_type}/connect", response_model=Envelope[dict[str, Any]]
)
async def connect_connector(
    connector_type: str, body: ConnectRequest, request: Request
) -> Envelope[dict[str, Any]]:
    try:
        await _connectivity(request).connect(connector_type, body.config)
    except ConnectivityError as err:
        raise _connectivity_error(err) from err
    return envelope({"connector_type": connector_type, "connected": True}, meta={"connected": True})


@router.post(
    "/connectivity/connectors/{connector_type}/disconnect",
    response_model=Envelope[dict[str, Any]],
)
async def disconnect_connector(connector_type: str, request: Request) -> Envelope[dict[str, Any]]:
    await _connectivity(request).disconnect(connector_type)
    return envelope(
        {"connector_type": connector_type, "connected": False}, meta={"connected": False}
    )


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
@router.post("/connectivity/discover", response_model=Envelope[list[dict[str, Any]]])
async def discover_devices(
    body: DiscoverRequest, request: Request
) -> Envelope[list[dict[str, Any]]]:
    home = await _smart_home(request).get_home(body.home_id)
    if home is None:
        raise HTTPException(status_code=404, detail=f"Home {body.home_id!r} does not exist.")
    try:
        devices = await _connectivity(request).run_discovery(body.connector_type, body.home_id)
    except ConnectivityError as err:
        raise _connectivity_error(err) from err
    payload = [_device_payload(d) for d in devices]
    return envelope(payload, meta={"count": len(payload)})


# ---------------------------------------------------------------------------
# State + commands
# ---------------------------------------------------------------------------
@router.post("/connectivity/devices/{device_id}/refresh", response_model=Envelope[dict[str, Any]])
async def refresh_device(device_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Reads the device's real state through its connector and updates
    its stored lifecycle status -- see ``ConnectivityService.
    refresh_device_state``. 404 if the device is unknown or was never
    discovered through a connector; 400 for a connector-level failure
    (not connected, unreachable)."""
    try:
        device = await _connectivity(request).refresh_device_state(device_id)
    except ConnectivityError as err:
        raise _connectivity_error(err) from err
    if device is None:
        raise HTTPException(
            status_code=404, detail=f"Device {device_id!r} is unknown or has no connector."
        )
    return envelope(_device_payload(device))


@router.post("/connectivity/devices/{device_id}/command", response_model=Envelope[dict[str, Any]])
async def send_device_command(
    device_id: str, body: SendCommandRequest, request: Request
) -> Envelope[dict[str, Any]]:
    """Generic, uninterpreted command passthrough -- see module
    docstring. ``success=False`` in the response body is a real,
    expected device-level outcome (still 200); only an unknown device or
    a connector-level failure is an error status."""
    from jarvis.core.exceptions import ServiceError

    try:
        result = await _connectivity(request).send_command(device_id, body.command, body.payload)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ConnectivityError as err:
        raise _connectivity_error(err) from err
    return envelope(
        {
            "external_id": result.external_id,
            "command": result.command,
            "success": result.success,
            "detail": result.detail,
        },
        meta={"success": result.success},
    )
