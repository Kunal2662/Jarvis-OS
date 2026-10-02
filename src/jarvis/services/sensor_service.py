"""Sensor service -- Milestone 12 Sensors.

The first **read-only** M12 module. No command translation, no
`ConnectivityService.send_command` calls anywhere in this file --
`docs/M12_SENSORS_LOGIC_CONTRACT.md` §4 defines exactly one capability
("read current state"), so unlike `SmartLightingService`/
`SmartLockService` there is no wire-format translation table here at
all; this module only *interprets* what a connector already reports
through `ConnectivityService.read_raw_state()` (shipped Task Group C).

**Every operation, including reads, requires the `smart_home`
permission** -- a deliberate departure from Smart Lighting/Smart
Locks, where only mutations are gated. See the Logic Contract §20 for
the full reasoning: no new permission scope is created (still the
existing `smart_home` scope, still the existing `PermissionModel`),
only a stricter application of it, because for a sensor *observing* is
the entire product, unlike a light or lock where the observable fact
(on/off, locked/unlocked) is comparatively low-stakes.
"""

from __future__ import annotations

import contextlib
import json
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import ConnectivityError

if TYPE_CHECKING:
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService

#: The `PermissionModel` identity this module declares and checks
#: against -- one fixed principal, mirroring `SMART_LIGHTING_PRINCIPAL`/
#: `SMART_LOCK_PRINCIPAL`'s exact naming and reasoning.
SENSOR_PRINCIPAL = "core:sensors"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- the same one Smart Lighting and Smart Locks
#: enforce for mutations; here it also gates reads (see module
#: docstring / Logic Contract §20).
SMART_HOME_SCOPE = "smart_home"

_SENSOR_DEVICE_TYPE = "sensor"

#: A connector's raw status string meaning "this device is down" --
#: MQTT's own `read_state()` already returns literally "offline" when
#: its availability-topic cache says so; Home Assistant's API reports
#: "unavailable" for a downed entity. Mirrors (does not import)
#: `connectivity_service.py`'s own private `_OFFLINE_STATUS_HINTS`, the
#: same "each module defines its own small heuristic" choice
#: `SmartLockService` already made.
_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})

_ON_VALUES = frozenset({"on", "true", "1"})
_OFF_VALUES = frozenset({"off", "false", "0"})

#: device_class -> (label when True, label when False). Closed and
#: deliberately non-exhaustive -- covers only the thirteen categories
#: the Logic Contract §3/§8 evaluated; anything else falls back to
#: `_DEFAULT_BINARY_LABELS` rather than guessing a pair nobody asked
#: for. Lives here, never in the domain layer -- see Logic Contract §8.
_BINARY_LABELS: dict[str, tuple[str, str]] = {
    "door": ("open", "closed"),
    "window": ("open", "closed"),
    "garage_door": ("open", "closed"),
    "motion": ("detected", "clear"),
    "smoke": ("detected", "clear"),
    "gas": ("detected", "clear"),
    "moisture": ("detected", "clear"),  # HA's real device_class for water leak.
    "vibration": ("detected", "clear"),
    "presence": ("occupied", "unoccupied"),
    "occupancy": ("occupied", "unoccupied"),
}
_DEFAULT_BINARY_LABELS = ("on", "off")


class SensorPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, so `routes/sensors.py` can
    tell "not granted" apart from "not found/wrong type" by exception
    type rather than by sniffing the message string. Mirrors
    `core/exceptions.py`'s own existing `AutomationPermissionDeniedError
    (AutomationError)` precedent, kept local to this module rather than
    added to the shared `core/exceptions.py` hierarchy since nothing
    outside `SensorService`/its route needs to catch it specifically --
    the same "define the narrow exception where it's used" choice
    `ConnectorRegistrationError` (`core/connectivity/registry.py`)
    already makes."""


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _kind_for(device: Device) -> str:
    """`"binary"` for a `binary_sensor`-domain device, `"numeric"`
    otherwise (including a device with no recorded domain/component --
    Logic Contract §4's "detect at use, not fabricate" default).

    Reads `metadata["domain"]` (HA-sourced discovery), falling back to
    `metadata["component"]` (MQTT-native discovery) -- the same
    fallback order every other `device_type="appliance"`/`"other"`
    service already uses (`ApplianceService`, `SirenService`,
    `AlarmControlPanelService`, the Water Heater service,
    `MediaPlayerService`, `VacuumHumidifierService`); restored here
    after being the one remaining M12 device category never backported
    to the convention (M0-M12 Structured Rework Audit, P1-2) --
    `MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
    never `metadata["domain"]`, so a bare `metadata["domain"]` lookup
    silently misclassified any MQTT-discovered binary sensor as
    numeric."""
    meta = _metadata(device)
    resolved = meta.get("domain") or meta.get("component")
    return "binary" if resolved == "binary_sensor" else "numeric"


def _device_class_for(device: Device) -> str | None:
    value = _metadata(device).get("device_class")
    return str(value) if value else None


def _parse_binary(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _ON_VALUES:
        return True
    if normalized in _OFF_VALUES:
        return False
    return None


def _parse_numeric(status: str) -> float | None:
    try:
        return float(status)
    except (TypeError, ValueError):
        return None


def _binary_state_label(device_class: str | None, value: bool | None) -> str | None:
    if value is None:
        return None
    true_label, false_label = _BINARY_LABELS.get(device_class or "", _DEFAULT_BINARY_LABELS)
    return true_label if value else false_label


def _numeric_state_label(value: float | None, unit: str | None) -> str | None:
    if value is None:
        return None
    return f"{value}{unit}" if unit else str(value)


def _sensor_list_payload(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "device_class": _device_class_for(device),
        "kind": _kind_for(device),
    }


def _sensor_full_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    kind = _kind_for(device)
    device_class = _device_class_for(device)
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "device_class": device_class,
        "kind": kind,
        "state": None,
        "value": None,
        "unit": None,
        "available": False,
        "timestamp": None,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    if payload["available"]:
        if kind == "binary":
            binary_value = _parse_binary(raw.status)
            payload["value"] = binary_value
            payload["state"] = _binary_state_label(device_class, binary_value)
        else:
            unit = raw.attributes.get("unit_of_measurement")
            unit_str = str(unit) if unit else None
            numeric_value = _parse_numeric(raw.status)
            payload["value"] = numeric_value
            payload["unit"] = unit_str
            payload["state"] = _numeric_state_label(numeric_value, unit_str)
    if raw.observed_at is not None:
        # Honest even when unavailable -- "last observed at" remains
        # true regardless of current reachability, unlike value/state
        # which would be misleading if shown while offline.
        payload["timestamp"] = raw.observed_at.isoformat()
    return payload


class SensorService:
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
        self._permissions.declare(SENSOR_PRINCIPAL, [SMART_HOME_SCOPE])

    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SENSOR_PRINCIPAL, SMART_HOME_SCOPE):
            raise SensorPermissionError(
                "Sensor access requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SENSOR_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SENSOR_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    async def _require_sensor(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _SENSOR_DEVICE_TYPE:
            raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a sensor.")
        return device

    async def list_sensors(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        sensor, the same list/detail asymmetry `SmartLightingService.
        list_lights`/`SmartLockService.list_locks` already draw."""
        self._require_permission()
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_SENSOR_DEVICE_TYPE
        )
        return [_sensor_list_payload(d) for d in devices]

    async def get_sensor_state(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        device = await self._require_sensor(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # fields (value=None, available=False) rather than fail the
        # read; mirrors `SmartLightingService.get_light_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _sensor_full_payload(device, raw)
