"""Camera service -- Milestone 12 Smart Cameras (Core Camera Slice).

The first pass on `device_type="camera"` -- already reserved in
`DEVICE_TYPES` (`domain/smart_home/models.py`) and already mapped by
both connectors (`HomeAssistantConnector`/`MqttConnector`'s own
`_DEVICE_DOMAINS`), so this module needs zero connector changes, the
same condition every prior M12 module-opening slice started from.

**Single device type, no domain discrimination** -- unlike Fan/Cover
(`device_type="appliance"`, told apart by `metadata["domain"]`), a
camera has no sibling category sharing its `device_type`, so this
module mirrors `SmartLockService`'s shape: `_require_camera` checks
`device_type` and nothing else.

**Four independent, zero-payload commands** (`turn_on`/`turn_off`/
`enable_motion_detection`/`disable_motion_detection`), mirroring
`SmartLockService`'s exact shape -- distinct verbs, not attributes that
combine, so no merged mutation method exists.

**Reads are permission-gated -- a deliberate departure from Lock/
Switch/Appliance/Thermostat, following `SensorService`'s precedent
instead.** Whether a camera is recording/streaming, and whether its
motion detection is armed, is itself privacy-/security-sensitive
information -- see `docs/M12_SMART_CAMERAS_LOGIC_CONTRACT.md` §4.

**`motion_detection` is `None`, never a fabricated `False`, when the
device does not report it.** HA's own `state_attributes` only adds
this key when the underlying property is truthy (confirmed directly
against `home-assistant/core`'s own source this session) -- so an
absent key means "unknown/unsupported", not "confirmed off".

**Not wired into `SmartHomeMemoryService` or `SecurityService`.**
Camera state is at least as privacy-sensitive as Sensor/Lock readings,
which `SmartHomeMemoryService`'s own Device-Category Expansion Slice
already permanently excluded; `SecurityService.trigger_panic_mode`'s
own docstring already states it never touches cameras.

**Live Streaming, Recording, Snapshot Capture, ML-driven Motion/Person/
Package/Vehicle Detection, and Face Recognition are all explicitly
deferred** -- see the Logic Contract §9 for why each needs new
architecture (binary storage, a security design, or a computer-vision
capability) this slice deliberately does not build.
"""

from __future__ import annotations

import contextlib
import enum
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import ConnectivityError
from jarvis.services.connectivity_service import connector_type_for

if TYPE_CHECKING:
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

#: The `PermissionModel` identity this module declares and checks
#: against -- one fixed principal, mirroring `SENSOR_PRINCIPAL`'s exact
#: naming and reasoning.
CAMERA_PRINCIPAL = "core:cameras"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- here it also gates reads, mirroring
#: `SensorService`'s identical departure from Lock/Switch/Appliance.
SMART_HOME_SCOPE = "smart_home"

_CAMERA_DEVICE_TYPE = "camera"

#: A connector's raw status string meaning "this device is down".
#: Mirrors (does not import) the same small heuristic every prior M12
#: module defines for itself.
_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})


class CameraPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, so `routes/cameras.py` can tell
    "not granted" apart from "not found/wrong type" by exception type
    rather than by sniffing the message string. Mirrors
    `SensorService.SensorPermissionError`'s identical reasoning, the
    same "define the narrow exception where it's used" choice."""


class CameraCommand(enum.StrEnum):
    """Four independent, zero-payload commands -- see module
    docstring."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    ENABLE_MOTION_DETECTION = "enable_motion_detection"
    DISABLE_MOTION_DETECTION = "disable_motion_detection"


def _translate_home_assistant(command: CameraCommand) -> tuple[str, dict[str, Any]]:
    """HA's own `camera`-domain service names, no payload -- verified
    directly against HA's public documentation and source this session
    (Logic Contract §3). Reached through the existing generic dispatcher
    (`HomeAssistantConnector.send_command` derives `domain` from
    `external_id.split(".", 1)[0]`) -- zero connector changes."""
    return command.value, {}


def _translate_mqtt(command: CameraCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines -- no prior MQTT
    consumer of camera commands existed. Reuses the identical literal
    strings for cross-connector predictability, the same choice every
    prior module's first MQTT consumer already made."""
    return command.value, {}


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _camera_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "state": None,
        "motion_detection": None,
        "available": False,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    if payload["available"]:
        # Open pass-through -- HA's own idle/recording/streaming state
        # string, never validated against a closed vocabulary (Logic
        # Contract §3, mirroring Vacuum's identical treatment).
        normalized = raw.status.strip().lower()
        payload["state"] = normalized or None
        attributes = raw.attributes or {}
        motion = attributes.get("motion_detection")
        # `None` (not `False`) when absent -- HA itself only adds this
        # key when truthy (Logic Contract §3); a missing key means
        # "unknown/unsupported", never a fabricated "confirmed off".
        payload["motion_detection"] = motion if isinstance(motion, bool) else None
    return payload


class CameraService:
    def __init__(
        self,
        *,
        smart_home: SmartHomeService,
        connectivity: ConnectivityService,
        permissions: PermissionModel,
    ) -> None:
        self._smart_home = smart_home
        self._connectivity = connectivity
        self._permissions = permissions
        self._permissions.declare(CAMERA_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(CAMERA_PRINCIPAL, SMART_HOME_SCOPE):
            raise CameraPermissionError(
                "Camera access requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{CAMERA_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{CAMERA_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Domain discrimination
    # ------------------------------------------------------------------
    async def _require_camera(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _CAMERA_DEVICE_TYPE:
            raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a camera.")
        return device

    # ------------------------------------------------------------------
    # Reads (gated -- Logic Contract §4)
    # ------------------------------------------------------------------
    async def list_cameras(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        camera, the same list/detail asymmetry every prior M12 module
        draws."""
        self._require_permission()
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_CAMERA_DEVICE_TYPE
        )
        return [_camera_payload(d) for d in devices]

    async def get_camera_state(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        device = await self._require_camera(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _camera_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands (gated)
    # ------------------------------------------------------------------
    async def turn_on(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, CameraCommand.TURN_ON)

    async def turn_off(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, CameraCommand.TURN_OFF)

    async def enable_motion_detection(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, CameraCommand.ENABLE_MOTION_DETECTION)

    async def disable_motion_detection(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, CameraCommand.DISABLE_MOTION_DETECTION)

    async def _send(self, device_id: str, command: CameraCommand) -> dict[str, Any]:
        device = await self._require_camera(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Cameras have no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}
