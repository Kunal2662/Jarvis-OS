"""Smart Switch service -- Milestone 12 Energy Management (Core Energy
Slice).

The thin orchestration layer `docs/M12_ENERGY_MANAGEMENT_LOGIC_CONTRACT.md`
requires: two normalized commands (`turn_on`, `turn_off`) translated
into each connector's wire format, through
:meth:`ConnectivityService.send_command` -- the same chokepoint every
other M12 caller already uses, never a second execution path. Mirrors
`services/smart_lock_service.py`'s exact shape (a single-attribute
device -- no attribute-merge case exists here either), reduced further
still: unlike locks, a switch is not physically safety-relevant, so no
`AgentSettings.confirm_required_tools` entry is added for it.

**No combined "SmartPlug" entity.** A physical smart plug that also
reports power/energy is, in this data model, one `device_type=
"switch"` row for control plus one or more sibling `device_type=
"sensor"` rows (`device_class="power"`/`"energy"`/...) for readings --
see module docstring's own Logic Contract §2. This service knows
nothing about those sibling sensor rows; it only ever operates on the
`switch` row itself.

**Energy/power readings are not this module's job.** Power Monitoring,
Energy Monitoring and Load Monitoring are already fully provided by
the shipped `SensorService` wherever the underlying connector exposes
the corresponding numeric sensor data -- nothing here duplicates that
normalization, and no `EnergySensorService`/`EnergyTelemetryService`/
`EnergyRegistry` exists.

**Permission enforcement reuses the existing Permission Engine.** Same
mechanism, same `smart_home` scope, a new fixed principal
(`core:smart_switch`, mirroring `core:smart_locks`'s naming) -- but
unlike Sensors, reads are **ungated** here, following the Smart
Lighting/Smart Locks precedent instead: a switch's on/off state carries
no comparable privacy weight to sensor data. See the Logic Contract §9
for the full reasoning.
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
#: against -- one fixed principal, mirroring
#: `smart_lock_service.SMART_LOCK_PRINCIPAL`'s exact naming and
#: reasoning.
SMART_SWITCH_PRINCIPAL = "core:smart_switch"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- the same one every other M12 module enforces
#: for mutations; switches are not separately scoped.
SMART_HOME_SCOPE = "smart_home"

_SWITCH_DEVICE_TYPE = "switch"


class SwitchCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"


def _translate_home_assistant(command: SwitchCommand) -> tuple[str, dict[str, Any]]:
    """HA's own switch-domain service names, no payload fields --
    verified directly against the shipped `HomeAssistantConnector.
    send_command` this session (domain/service split from `entity_id`,
    body = `{"entity_id": ..., **payload}`)."""
    return command.value, {}


def _translate_mqtt(command: SwitchCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines, deliberately
    mirroring HA's own switch-domain service names
    (`turn_on`/`turn_off`) for cross-connector predictability -- the
    same choice `smart_lock_service._translate_mqtt` made for
    `lock`/`unlock`. Verified against the shipped `MqttConnector.
    send_command`/`build_command_envelope` this session."""
    return command.value, {}


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _infer_on(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in {"on", "true", "1"}:
        return True
    if normalized in {"off", "false", "0"}:
        return False
    return None


def _switch_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "on": None,
        "available": raw is not None,
    }
    if raw is not None:
        payload["available"] = raw.status.strip().lower() not in {"offline", "unavailable"}
        if payload["available"]:
            payload["on"] = _infer_on(raw.status)
    return payload


class SmartSwitchService:
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
        self._permissions.declare(SMART_SWITCH_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SMART_SWITCH_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Smart Switch control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SMART_SWITCH_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SMART_SWITCH_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads (ungated -- see module docstring)
    # ------------------------------------------------------------------
    async def _require_switch(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _SWITCH_DEVICE_TYPE:
            raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a switch.")
        return device

    async def list_switches(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        switch, the same list/detail asymmetry `SmartLockService.
        list_locks` already draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_SWITCH_DEVICE_TYPE
        )
        return [_switch_payload(d) for d in devices]

    async def get_switch_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_switch(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state rather than fail the read; mirrors `SmartLockService.
        # get_lock_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _switch_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def turn_on(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, SwitchCommand.TURN_ON)

    async def turn_off(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, SwitchCommand.TURN_OFF)

    async def _send(self, device_id: str, command: SwitchCommand) -> dict[str, Any]:
        device = await self._require_switch(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Smart Switch has no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}
