"""Device Simulator connector -- Milestone 12 Developer Tools (Device
Simulator Slice).

**Option C, not a new `CONNECTOR_TYPES` entry** (see `docs/
M12_DEVELOPER_TOOLS_DEVICE_SIMULATOR_LOGIC_CONTRACT.md` §2). This class
structurally satisfies `IDeviceConnector` exactly like
`HomeAssistantConnector`/`MqttConnector`, but is never registered under
a new registry key -- the DI composition root instead registers *this*
factory under the existing `"home_assistant"` key when Developer Tools
simulator mode is on (`Settings.devtools.simulator_enabled`), swapping
out `HomeAssistantConnector`'s own factory entirely for that one slot.
This is deliberate: every device-category service's own `_TRANSLATORS`
dict (`smart_lighting_service.py`, `smart_switch_service.py`,
`thermostat_service.py`, `smart_lock_service.py`) is a closed
`{"home_assistant": ..., "mqtt": ...}` mapping -- a genuinely new
connector-type string would make every mutation path raise "no command
translation" before ever reaching this class, since those services are
deliberately not modified by this task group. Reusing the existing
`"home_assistant"` key means every one of those translators already
works, unmodified.

**`connector_type = "home_assistant"`** matches the registry key this
class is registered under when simulator mode is active -- consistent
labeling, not a functional requirement (nothing in `ConnectivityService`
or `routes/connectivity.py` reads a connector instance's own
`connector_type` attribute externally; every live lookup uses the
registry-key string the caller supplied).

**State/command vocabulary is deliberately Home Assistant's own** --
the exact status/attribute shape (`on`/`off`/`locked`/`unlocked`
status strings; `brightness`/`color_temp_kelvin`/`rgb_color`/
`current_temperature`/`temperature`/`hvac_modes`/`min_temp`/`max_temp`
attribute keys) and command names (`turn_on`/`turn_off`,
`set_hvac_mode`/`set_temperature`, `lock`/`unlock`) every relevant
device-category service's own HA translator/normalization logic
already expects and is tested against -- not a third, simulator-
specific vocabulary invented from nothing.

**Real-world safety.** This module never imports `httpx`, `gmqtt`,
`HomeAssistantConnector`, `MqttConnector`, or
`ConnectorCredentialStore` -- every command terminates inside this
class's own in-memory state. There is no code path here by which a
real network call, real device, or real credential could ever be
reached.

**Ephemeral by design.** The device roster this class holds
(`self._devices`) is a plain in-memory dict, mirroring
`MqttConnector`'s own `_state_cache` precedent for a connector's live
state -- lost on process restart, never written to the database. A
device *imported* through the normal `ConnectivityService.
run_discovery` -> `SmartHomeService.register_discovered_device` path
becomes an ordinary `Device` row in the existing, unmodified
`smart_home_devices` table, exactly like a real Home-Assistant-sourced
device -- no schema change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from jarvis.core.interfaces.connectivity import (
    CommandResult,
    ConnectivityError,
    ConnectorNotConnectedError,
    DeviceState,
    DiscoveredDevice,
)

#: The MVP simulated device-category vocabulary -- Logic Contract §5.
#: Deliberately not every `DEVICE_TYPES` value: these five are exactly
#: the categories with a unique `device_type` needing no
#: `metadata["domain"]`/`["component"]` fallback resolution, the same
#: "simple dispatch" boundary Task Group O (Smart Home Memory)
#: independently arrived at for an unrelated reason.
SIMULATED_DEVICE_TYPES: frozenset[str] = frozenset(
    {"light", "switch", "thermostat", "lock", "sensor"}
)


def _default_state(device_type: str) -> tuple[str, dict[str, Any]]:
    """The deterministic initial status/attributes for a freshly
    defined device of *device_type*, in Home Assistant's own
    vocabulary -- never random."""
    if device_type == "light":
        return "off", {}
    if device_type == "switch":
        return "off", {}
    if device_type == "thermostat":
        return "off", {
            "current_temperature": 21.0,
            "temperature": 21.0,
            "hvac_modes": ["off", "heat", "cool"],
            "min_temp": 10.0,
            "max_temp": 32.0,
        }
    if device_type == "lock":
        return "unlocked", {}
    if device_type == "sensor":
        return "on", {}
    raise ConnectivityError(
        f"simulator: unsupported device_type {device_type!r}; "
        f"allowed: {sorted(SIMULATED_DEVICE_TYPES)}."
    )


@dataclass
class _SimulatedDevice:
    external_id: str
    device_type: str
    name: str
    #: Merged into `DiscoveredDevice.metadata` at `discover()` time --
    #: only sensors use this (`domain`/`device_class`), mirroring
    #: exactly what a real HA-Discovery-sourced sensor device already
    #: carries (`sensor_service.py`'s own `_kind_for`/`_device_class_for`).
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)
    unavailable: bool = False
    force_command_failure: bool = False
    failure_detail: str = ""


def _handle_light(
    device: _SimulatedDevice, command: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    if command == "turn_on":
        device.status = "on"
        for key in ("brightness_pct", "color_temp_kelvin", "rgb_color"):
            if key in payload:
                attr = "brightness" if key == "brightness_pct" else key
                device.attributes[attr] = payload[key]
        return True, ""
    if command == "turn_off":
        device.status = "off"
        return True, ""
    return False, f"unsupported command {command!r} for a light"


def _handle_switch(
    device: _SimulatedDevice, command: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    if command == "turn_on":
        device.status = "on"
        return True, ""
    if command == "turn_off":
        device.status = "off"
        return True, ""
    return False, f"unsupported command {command!r} for a switch"


def _handle_thermostat(
    device: _SimulatedDevice, command: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    if command == "set_hvac_mode":
        mode = payload.get("hvac_mode")
        if not mode:
            return False, "set_hvac_mode requires a non-empty 'hvac_mode'."
        device.status = str(mode)
        return True, ""
    if command == "set_temperature":
        if "temperature" not in payload:
            return False, "set_temperature requires a 'temperature'."
        device.attributes["temperature"] = payload["temperature"]
        return True, ""
    return False, f"unsupported command {command!r} for a thermostat"


def _handle_lock(
    device: _SimulatedDevice, command: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    if command == "lock":
        device.status = "locked"
        return True, ""
    if command == "unlock":
        device.status = "unlocked"
        return True, ""
    return False, f"unsupported command {command!r} for a lock"


def _handle_sensor(
    device: _SimulatedDevice, command: str, payload: dict[str, Any]
) -> tuple[bool, str]:
    return False, "sensor devices do not accept commands"


#: device_type -> command handler. Closed to `SIMULATED_DEVICE_TYPES`
#: by construction, mirroring every real device-category service's own
#: closed `_TRANSLATORS` dict.
_COMMAND_HANDLERS: dict[str, Any] = {
    "light": _handle_light,
    "switch": _handle_switch,
    "thermostat": _handle_thermostat,
    "lock": _handle_lock,
    "sensor": _handle_sensor,
}


class SimulatorConnector:
    """Structurally satisfies `IDeviceConnector` -- no inheritance,
    matching every other adapter in this codebase. See module
    docstring for why `connector_type` is `"home_assistant"` and why
    this is not a fourth `CONNECTOR_TYPES` entry."""

    connector_type = "home_assistant"

    def __init__(self) -> None:
        self._connected = False
        self._devices: dict[str, _SimulatedDevice] = {}

    # ------------------------------------------------------------------
    # IDeviceConnector protocol
    # ------------------------------------------------------------------
    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def discover(self) -> list[DiscoveredDevice]:
        if not self._connected:
            raise ConnectorNotConnectedError("simulator is not connected.")
        return [
            DiscoveredDevice(
                external_id=d.external_id,
                name=d.name,
                device_type=d.device_type,
                metadata=dict(d.metadata),
            )
            for d in self._devices.values()
        ]

    async def read_state(self, external_id: str) -> DeviceState:
        if not self._connected:
            raise ConnectorNotConnectedError("simulator is not connected.")
        device = self._devices.get(external_id)
        if device is None:
            raise ConnectivityError(f"simulator: unknown device {external_id!r}.")
        status = "unavailable" if device.unavailable else device.status
        return DeviceState(
            external_id=external_id, status=status, attributes=dict(device.attributes)
        )

    async def send_command(
        self, external_id: str, command: str, payload: dict[str, Any]
    ) -> CommandResult:
        if not self._connected:
            raise ConnectorNotConnectedError("simulator is not connected.")
        device = self._devices.get(external_id)
        if device is None:
            raise ConnectivityError(f"simulator: unknown device {external_id!r}.")
        if device.unavailable:
            return CommandResult(
                external_id=external_id, command=command, success=False, detail="device unavailable"
            )
        if device.force_command_failure:
            return CommandResult(
                external_id=external_id,
                command=command,
                success=False,
                detail=device.failure_detail or "simulated command failure",
            )
        handler = _COMMAND_HANDLERS[device.device_type]
        success, detail = handler(device, command, payload)
        return CommandResult(
            external_id=external_id, command=command, success=success, detail=detail
        )

    # ------------------------------------------------------------------
    # Devtools roster management -- not part of IDeviceConnector, used
    # only by routes/devtools.py's own simulator endpoints.
    # ------------------------------------------------------------------
    def define_device(
        self,
        *,
        device_type: str,
        external_id: str | None = None,
        name: str | None = None,
        status: str | None = None,
        attributes: dict[str, Any] | None = None,
        device_class: str | None = None,
        binary: bool = False,
    ) -> dict[str, Any]:
        """(Re)defines one simulated device from scratch -- a `POST`
        always fully sets the device's shape, it never incrementally
        patches an existing one, for predictable, deterministic test
        setup."""
        if device_type not in SIMULATED_DEVICE_TYPES:
            raise ConnectivityError(
                f"simulator: unsupported device_type {device_type!r}; "
                f"allowed: {sorted(SIMULATED_DEVICE_TYPES)}."
            )
        eid = external_id or f"simulator.{device_type}.{uuid4().hex[:8]}"
        default_status, default_attrs = _default_state(device_type)
        metadata: dict[str, Any] = {}
        if device_type == "sensor":
            if binary:
                metadata["domain"] = "binary_sensor"
            if device_class:
                metadata["device_class"] = device_class
        record = _SimulatedDevice(
            external_id=eid,
            device_type=device_type,
            name=name or f"Simulated {device_type.capitalize()}",
            metadata=metadata,
            status=status if status is not None else default_status,
            attributes={**default_attrs, **(attributes or {})},
        )
        self._devices[eid] = record
        return self._public(record)

    def list_devices(self) -> list[dict[str, Any]]:
        return [self._public(d) for d in self._devices.values()]

    def delete_device(self, external_id: str) -> bool:
        return self._devices.pop(external_id, None) is not None

    def set_fault(
        self,
        external_id: str,
        *,
        unavailable: bool | None = None,
        force_command_failure: bool | None = None,
        failure_detail: str | None = None,
    ) -> dict[str, Any]:
        device = self._devices.get(external_id)
        if device is None:
            raise ConnectivityError(f"simulator: unknown device {external_id!r}.")
        if unavailable is not None:
            device.unavailable = unavailable
        if force_command_failure is not None:
            device.force_command_failure = force_command_failure
        if failure_detail is not None:
            device.failure_detail = failure_detail
        return self._public(device)

    def reset(self) -> int:
        count = len(self._devices)
        self._devices.clear()
        return count

    def _public(self, device: _SimulatedDevice) -> dict[str, Any]:
        return {
            "external_id": device.external_id,
            "device_type": device.device_type,
            "name": device.name,
            "status": device.status,
            "attributes": dict(device.attributes),
            "unavailable": device.unavailable,
            "force_command_failure": device.force_command_failure,
            "failure_detail": device.failure_detail,
        }
