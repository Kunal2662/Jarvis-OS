"""Appliance service -- Milestone 12 Appliance Control (Core Appliance
Slice: Fans + Covers; Fan Percentage + Cover Position Slice).

The thin orchestration layer `docs/M12_APPLIANCE_CONTROL_LOGIC_CONTRACT.
md` requires: normalized commands (`turn_on`/`turn_off` for fans,
`open_cover`/`close_cover` for covers, plus `set_percentage`/
`set_cover_position` per `docs/
M12_APPLIANCE_FAN_COVER_POSITION_LOGIC_CONTRACT.md`) translated into
each connector's wire format, through :meth:`ConnectivityService.
send_command` -- the same chokepoint every other M12 caller already
uses, never a second execution path.

**One service, two capabilities -- not two services, and not a generic
`ApplianceService` built to grow indefinitely.** Fans and covers share
one `device_type` (`"appliance"`) and one connector mapping; they are
told apart by `Device.metadata_json["domain"]` (`"fan"` vs `"cover"`),
the same domain-discrimination mechanism `SensorService._kind_for`
already established for `binary_sensor` vs `sensor` -- see the Logic
Contract §4. This module only ever knows about fan and cover; a future
appliance category (climate, media_player, vacuum, water_heater,
humidifier) gets its own Logic Contract and, per that contract, likely
its own service -- not a new branch bolted onto this one.

**Percentage/position, not merged into `turn_on`/`open_cover`.**
`fan.set_percentage` and `cover.set_cover_position` are each their own
real, separate Home Assistant service -- unlike `light.turn_on`, which
is the *only* way HA lets a caller set brightness, HA never requires
(or accepts) `percentage`/`position` as a parameter of `fan.turn_on`/
`cover.open_cover`. `set_fan_percentage`/`set_cover_position` therefore
each send exactly one, standalone wire command -- never an implicit
accompanying `turn_on`/`open_cover` this module did not ask for. See
the Fan Percentage + Cover Position Logic Contract §6 for the full
"why Lighting's own translator shape applies here, but its
merge-into-turn_on *behavior* does not" reasoning.

**Permission enforcement reuses the existing Permission Engine.** Same
mechanism, same `smart_home` scope, one fixed principal
(`core:appliances`, covering both capabilities -- one principal per
module, mirroring `core:smart_switch`) -- reads are **ungated**, mirroring
the Smart Lighting/Smart Locks/Smart Switches precedent, not Sensors'.
See the Logic Contract §14 for the full reasoning.
"""

from __future__ import annotations

import contextlib
import enum
import json
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
#: against -- one fixed principal covering both fan and cover commands,
#: mirroring `smart_switch_service.SMART_SWITCH_PRINCIPAL`'s exact
#: naming and one-principal-per-module reasoning.
APPLIANCE_PRINCIPAL = "core:appliances"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- the same one every other M12 module enforces
#: for mutations; appliances are not separately scoped.
SMART_HOME_SCOPE = "smart_home"

_APPLIANCE_DEVICE_TYPE = "appliance"
_FAN_DOMAIN = "fan"
_COVER_DOMAIN = "cover"


class FanCommand(enum.StrEnum):
    """The normalized fan command vocabulary this module supports."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    SET_PERCENTAGE = "set_percentage"


class CoverCommand(enum.StrEnum):
    """The normalized cover command vocabulary this module supports."""

    OPEN = "open_cover"
    CLOSE = "close_cover"
    SET_POSITION = "set_cover_position"


def _translate_home_assistant(
    command: FanCommand | CoverCommand, *, value: int | None = None
) -> tuple[str, dict[str, Any]]:
    """HA's own fan-/cover-domain service names -- verified directly
    against the shipped `HomeAssistantConnector.send_command` this
    session (domain/service split from `entity_id`, body =
    `{"entity_id": ..., **payload}`). See the Logic Contract §8/§9.
    `turn_on`/`turn_off`/`open_cover`/`close_cover` carry no payload,
    unchanged. `set_percentage`/`set_cover_position` carry exactly the
    one value HA's own `fan.set_percentage`/`cover.set_cover_position`
    services accept (`percentage`/`position`, externally verified
    0-100 integers -- Fan Percentage + Cover Position Logic Contract
    §8) -- no scale conversion, unlike Lighting's own brightness_pct
    split, since this module's normalized range already matches HA's."""
    if value is not None:
        key = "percentage" if command is FanCommand.SET_PERCENTAGE else "position"
        return command.value, {key: value}
    return command.value, {}


def _translate_mqtt(
    command: FanCommand | CoverCommand, *, value: int | None = None
) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines, deliberately
    mirroring HA's own service names for cross-connector predictability
    -- the same choice `smart_lock_service._translate_mqtt`/
    `smart_switch_service._translate_mqtt` already made, now extended to
    `set_percentage`/`set_cover_position` the same way (Fan Percentage +
    Cover Position Logic Contract §9 -- no repository or spec defines a
    standard MQTT equivalent, so this module defines its own, mirroring
    HA's names/payload keys exactly). Verified against the shipped
    `MqttConnector.send_command`/`build_command_envelope` this
    session."""
    if value is not None:
        key = "percentage" if command is FanCommand.SET_PERCENTAGE else "position"
        return command.value, {key: value}
    return command.value, {}


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op. Shared by both fan and cover commands -- both translators are
#: no-op passthroughs of `command.value`, so one dict serves either enum.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}

#: HA's real `cover`-domain entity state vocabulary -- anything else
#: (including an empty/unrecognized string) reports `state=None` rather
#: than fabricating a value the connector layer itself does not
#: represent, the same "detect at use, not fabricate" discipline
#: `SmartLockService._infer_locked` already applies.
_COVER_STATE_VALUES = frozenset({"open", "closed", "opening", "closing"})

_ON_VALUES = frozenset({"on", "true", "1"})
_OFF_VALUES = frozenset({"off", "false", "0"})
_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _domain_for(device: Device) -> str | None:
    value = _metadata(device).get("domain")
    return str(value) if value else None


def _infer_on(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _ON_VALUES:
        return True
    if normalized in _OFF_VALUES:
        return False
    return None


def _infer_cover_state(status: str) -> str | None:
    normalized = status.strip().lower()
    return normalized if normalized in _COVER_STATE_VALUES else None


def _coerce_int(value: Any) -> int | None:
    """`None` for anything unparseable -- never a silently wrong `0`.
    `bool` is rejected explicitly since it is an `int` subclass --
    mirrors `water_heater_service._coerce_float`'s own exact defensive
    shape (Fan Percentage + Cover Position Logic Contract §7), a new
    local helper since `percentage`/`position` are integer quantities
    per HA's own type declaration, unlike the float-valued attributes
    (temperature, humidity, battery level) the existing per-module
    `_coerce_float` copies already handle."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_percent_range(value: int, field_name: str) -> None:
    """Shared by `percentage` and `position` -- both are 0-100
    integers with identical validation rules (Fan Percentage + Cover
    Position Logic Contract §14). `bool` rejected explicitly, mirroring
    `smart_lighting_service._validate_brightness`'s own guard against
    the `bool`-is-`int`-subclass gotcha."""
    if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= 100):
        raise ServiceError(f"{field_name} must be an integer 0-100; got {value!r}.")


def _fan_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "percentage": None,
        "available": raw is not None,
    }
    if raw is not None:
        payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
        if payload["available"]:
            payload["on"] = _infer_on(raw.status)
            attributes = raw.attributes or {}
            payload["percentage"] = _coerce_int(attributes.get("percentage"))
    return payload


def _cover_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "position": None,
        "available": raw is not None,
    }
    if raw is not None:
        payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
        if payload["available"]:
            payload["state"] = _infer_cover_state(raw.status)
            attributes = raw.attributes or {}
            payload["position"] = _coerce_int(attributes.get("current_cover_position"))
    return payload


class ApplianceService:
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
        self._permissions.declare(APPLIANCE_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(APPLIANCE_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Appliance control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{APPLIANCE_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{APPLIANCE_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Domain discrimination (see Logic Contract §4)
    # ------------------------------------------------------------------
    async def _require_fan(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _APPLIANCE_DEVICE_TYPE or _domain_for(device) != _FAN_DOMAIN:
            raise ServiceError(f"Device {device_id!r} is not a fan.")
        return device

    async def _require_cover(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _APPLIANCE_DEVICE_TYPE or _domain_for(device) != _COVER_DOMAIN:
            raise ServiceError(f"Device {device_id!r} is not a cover.")
        return device

    # ------------------------------------------------------------------
    # Fans -- reads (ungated -- see Logic Contract §14)
    # ------------------------------------------------------------------
    async def list_fans(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per fan,
        the same list/detail asymmetry every prior M12 module already
        draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_fan_payload(d) for d in devices if _domain_for(d) == _FAN_DOMAIN]

    async def get_fan_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_fan(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state rather than fail the read; mirrors `SmartSwitchService.
        # get_switch_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _fan_payload(device, raw)

    # ------------------------------------------------------------------
    # Fans -- commands
    # ------------------------------------------------------------------
    async def fan_on(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_fan(device_id, FanCommand.TURN_ON)

    async def fan_off(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_fan(device_id, FanCommand.TURN_OFF)

    async def set_fan_percentage(self, device_id: str, percentage: int) -> dict[str, Any]:
        """Sends exactly one `set_percentage` wire command -- never an
        implicit accompanying `turn_on` (Fan Percentage + Cover
        Position Logic Contract §4/§6). `percentage=0` is a valid,
        literal value, not a stand-in for `turn_off`."""
        self._require_permission()
        _validate_percent_range(percentage, "percentage")
        return await self._send_fan(device_id, FanCommand.SET_PERCENTAGE, value=percentage)

    async def _send_fan(
        self, device_id: str, command: FanCommand, *, value: int | None = None
    ) -> dict[str, Any]:
        device = await self._require_fan(device_id)
        return await self._send(device, command, value=value)

    # ------------------------------------------------------------------
    # Covers -- reads (ungated -- see Logic Contract §14)
    # ------------------------------------------------------------------
    async def list_covers(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        cover, the same list/detail asymmetry every prior M12 module
        already draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_cover_payload(d) for d in devices if _domain_for(d) == _COVER_DOMAIN]

    async def get_cover_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_cover(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _cover_payload(device, raw)

    # ------------------------------------------------------------------
    # Covers -- commands
    # ------------------------------------------------------------------
    async def cover_open(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_cover(device_id, CoverCommand.OPEN)

    async def cover_close(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_cover(device_id, CoverCommand.CLOSE)

    async def set_cover_position(self, device_id: str, position: int) -> dict[str, Any]:
        """Sends exactly one `set_cover_position` wire command -- never
        an implicit accompanying `open_cover`/`close_cover` (Fan
        Percentage + Cover Position Logic Contract §5/§6). `position=0`
        (closed) and `position=100` (open) are both ordinary, valid
        values, not special-cased."""
        self._require_permission()
        _validate_percent_range(position, "position")
        return await self._send_cover(device_id, CoverCommand.SET_POSITION, value=position)

    async def _send_cover(
        self, device_id: str, command: CoverCommand, *, value: int | None = None
    ) -> dict[str, Any]:
        device = await self._require_cover(device_id)
        return await self._send(device, command, value=value)

    # ------------------------------------------------------------------
    # Shared command dispatch
    # ------------------------------------------------------------------
    async def _send(
        self, device: Device, command: FanCommand | CoverCommand, *, value: int | None = None
    ) -> dict[str, Any]:
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device.id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Appliance Control has no command translation for connector "
                f"type {connector_type!r}."
            )
        wire_command, payload = translator(command, value=value)
        result = await self._connectivity.send_command(device.id, wire_command, payload)
        return {"device_id": device.id, "success": result.success, "detail": result.detail}
