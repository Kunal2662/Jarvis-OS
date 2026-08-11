"""Vacuum + Humidifier service -- Milestone 12 Appliance Control
(Vacuum + Humidifier Core Slice).

**Deliberately not an `ApplianceService` extension.** `ApplianceService`'s
own module docstring already establishes the rule this module follows:
"a future appliance category (climate, media_player, vacuum,
water_heater, humidifier) gets its own Logic Contract and, per that
contract, likely its own service -- not a new branch bolted onto this
one." Both categories still share `device_type="appliance"` with
Fan/Cover (unlike Climate, which got its own `device_type`), so this
module mirrors `ApplianceService`'s own domain-discrimination shape
(`docs/M12_APPLIANCE_VACUUM_HUMIDIFIER_LOGIC_CONTRACT.md` §14) rather
than `ThermostatService`'s.

**The MQTT `component`/`domain` fix lives here, and only here.**
`MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
never `metadata["domain"]` -- verified this session, and a real,
pre-existing gap in already-shipped `ApplianceService._domain_for`
(Fan/Cover) too, left unfixed there by explicit instruction (Logic
Contract §3.1 -- a separate, narrower follow-up). This module's own
`_domain_for` checks `metadata["domain"]` first, falling back to
`metadata["component"]`: MQTT's `component` segment is populated with
the identical domain vocabulary HA's own REST connector calls
`domain` (`_HA_COMPONENT_DEVICE_TYPES`'s keys are identical to
`_DEVICE_DOMAINS`'s), so this is a safe, narrow extension of the
existing "detect at use, not fabricate" discipline applied to a
metadata *key* lookup, not a new mechanism.

**Vacuum**: four independent, zero-payload commands (`start`/`stop`/
`pause`/`return_to_base`), mirroring `FanCommand`/`CoverCommand`'s
shape -- distinct verbs, not attributes that combine, so no merged
mutation method exists for it. `state` is an open pass-through string,
never validated against a closed vocabulary (Vacuum's real state
vocabulary has zero repository evidence, unlike Cover's small,
HA-standard set).

**Humidifier**: one merged mutation, `set_humidifier_state(on?,
target_humidity?)`, mirroring `ThermostatService.set_thermostat_state`'s
shape. HA has no known merged service accepting both at once, so a
combined update sends two sequential calls, on/off first (unlike
Thermostat's mode-first ordering -- a humidifier's on/off state does
not change what a humidity setpoint means, so the order is a
readability convention, not a correctness requirement). `mode` is
reported when the device provides it but is **read-only** in this
MVP -- see Logic Contract §8 for the full reasoning.

**No invented limits or vocabulary.** Humidity bounds are enforced only
when the device itself reports `min_humidity`/`max_humidity`; mode has
no fixed enum.
"""

from __future__ import annotations

import contextlib
import enum
import json
import math
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
#: against -- one principal covering both capabilities, mirroring
#: `APPLIANCE_PRINCIPAL`'s one-principal-per-module reasoning. Named
#: precisely after what it covers (not the vaguer "core:home_appliances"
#: originally proposed) to avoid confusion with the already-existing
#: `core:appliances` (Fan/Cover) -- Logic Contract §13.
VACUUM_HUMIDIFIER_PRINCIPAL = "core:vacuum_humidifier"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

_APPLIANCE_DEVICE_TYPE = "appliance"
_VACUUM_DOMAIN = "vacuum"
_HUMIDIFIER_DOMAIN = "humidifier"

_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})
_ON_VALUES = frozenset({"on", "true", "1"})
_OFF_VALUES = frozenset({"off", "false", "0"})


class VacuumCommand(enum.StrEnum):
    """Four independent, zero-payload commands -- see module docstring."""

    START = "start"
    STOP = "stop"
    PAUSE = "pause"
    RETURN_TO_BASE = "return_to_base"


def _translate_vacuum_home_assistant(command: VacuumCommand) -> tuple[str, dict[str, Any]]:
    """HA's own `vacuum`-domain service names -- confirmed against HA's
    public documentation this session (start/stop/pause/return_to_base,
    each zero-payload); this repository carries no prior reference to
    any of them, so this remains the first time they are exercised
    here. Reached through the existing generic dispatcher
    (`HomeAssistantConnector.send_command` derives `domain` from
    `external_id.split(".", 1)[0]`) -- zero connector changes."""
    return command.value, {}


def _translate_vacuum_mqtt(command: VacuumCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines -- no prior MQTT
    consumer of vacuum commands existed. Reuses the identical literal
    strings for cross-connector predictability, the same choice
    Fan/Cover/Thermostat already made."""
    return command.value, {}


_VACUUM_TRANSLATORS = {
    "home_assistant": _translate_vacuum_home_assistant,
    "mqtt": _translate_vacuum_mqtt,
}


def _translate_humidifier_home_assistant(
    *, on: bool | None, target_humidity: float | None
) -> list[tuple[str, dict[str, Any]]]:
    """HA's own humidifier-domain service names -- `turn_on`/`turn_off`/
    `set_humidity` (payload `{"humidity": <value>}`), confirmed against
    HA's public documentation this session. **Two calls for a combined
    update**, on/off first -- Logic Contract §9's documented ordering,
    chosen because no HA service is known to accept both in one call
    (the same fallback shape `ThermostatService` uses for
    `set_hvac_mode`/`set_temperature`, reused here)."""
    calls: list[tuple[str, dict[str, Any]]] = []
    if on is True:
        calls.append(("turn_on", {}))
    elif on is False:
        calls.append(("turn_off", {}))
    if target_humidity is not None:
        calls.append(("set_humidity", {"humidity": target_humidity}))
    return calls


def _translate_humidifier_mqtt(
    *, on: bool | None, target_humidity: float | None
) -> list[tuple[str, dict[str, Any]]]:
    """A JARVIS-native vocabulary this module defines -- always one
    merged `set_state` call, mirroring `SmartLightingService`'s/
    `ThermostatService`'s own MQTT convention. MQTT's envelope has no
    constraint requiring two calls the way HA's two-service model
    does."""
    args: dict[str, Any] = {}
    if on is not None:
        args["on"] = on
    if target_humidity is not None:
        args["target_humidity"] = target_humidity
    return [("set_state", args)]


_HUMIDIFIER_TRANSLATORS = {
    "home_assistant": _translate_humidifier_home_assistant,
    "mqtt": _translate_humidifier_mqtt,
}


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _domain_for(device: Device) -> str | None:
    """`metadata["domain"]` first (HA REST discovery, and MQTT's own
    JARVIS-native envelope when firmware chooses to set it); falls back
    to `metadata["component"]` (MQTT HA-Discovery's own key for the
    identical domain vocabulary) -- see module docstring and Logic
    Contract §3. Local to this module by design; not shared with
    `appliance_service.py`."""
    metadata = _metadata(device)
    value = metadata.get("domain") or metadata.get("component")
    return str(value) if value else None


def _coerce_float(value: Any) -> float | None:
    """`None` for anything unparseable -- never a silently wrong `0.0`.
    `bool` is rejected explicitly since it is an `int` subclass."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) or math.isinf(parsed) else parsed


def _infer_on(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _ON_VALUES:
        return True
    if normalized in _OFF_VALUES:
        return False
    return None


def _validate_target_humidity(value: Any) -> float:
    """Rejects `bool`, non-numerics, NaN and +/-inf. Imposes no range
    of its own -- device-reported `min_humidity`/`max_humidity` are the
    only bounds ever enforced, mirroring `ThermostatService`'s identical
    rule for temperature."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(f"target_humidity must be a number; got {value!r}.")
    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ServiceError(f"target_humidity must be a finite number; got {value!r}.")
    return parsed


def _vacuum_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "battery_level": None,
        "available": False,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    if payload["available"]:
        # Open pass-through -- never validated against a closed
        # vocabulary; unlike Cover, Vacuum's real state vocabulary has
        # zero repository evidence (Logic Contract §5).
        normalized = raw.status.strip().lower()
        payload["state"] = normalized or None
    attributes = raw.attributes or {}
    payload["battery_level"] = _coerce_float(attributes.get("battery_level"))
    return payload


def _humidifier_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "current_humidity": None,
        "target_humidity": None,
        "mode": None,
        "min_humidity": None,
        "max_humidity": None,
        "available": False,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    attributes = raw.attributes or {}
    # Capability fields survive unavailability -- they describe the
    # device's declared range/mode, not its live reading (mirrors
    # ThermostatService's identical rule for hvac_modes/min_temp/max_temp).
    mode = attributes.get("mode")
    payload["mode"] = str(mode) if isinstance(mode, str) and mode.strip() else None
    payload["min_humidity"] = _coerce_float(attributes.get("min_humidity"))
    payload["max_humidity"] = _coerce_float(attributes.get("max_humidity"))
    if payload["available"]:
        payload["on"] = _infer_on(raw.status)
        payload["current_humidity"] = _coerce_float(attributes.get("current_humidity"))
        payload["target_humidity"] = _coerce_float(attributes.get("humidity"))
    return payload


class VacuumHumidifierService:
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
        self._permissions.declare(VACUUM_HUMIDIFIER_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(VACUUM_HUMIDIFIER_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Vacuum/Humidifier control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{VACUUM_HUMIDIFIER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{VACUUM_HUMIDIFIER_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Domain discrimination
    # ------------------------------------------------------------------
    async def _require_vacuum(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _APPLIANCE_DEVICE_TYPE or _domain_for(device) != _VACUUM_DOMAIN:
            raise ServiceError(f"Device {device_id!r} is not a vacuum.")
        return device

    async def _require_humidifier(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if (
            device.device_type != _APPLIANCE_DEVICE_TYPE
            or _domain_for(device) != _HUMIDIFIER_DOMAIN
        ):
            raise ServiceError(f"Device {device_id!r} is not a humidifier.")
        return device

    # ------------------------------------------------------------------
    # Vacuum -- reads (ungated -- Logic Contract §13)
    # ------------------------------------------------------------------
    async def list_vacuums(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        vacuum, the same list/detail asymmetry every prior M12 module
        draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_vacuum_payload(d) for d in devices if _domain_for(d) == _VACUUM_DOMAIN]

    async def get_vacuum_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_vacuum(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _vacuum_payload(device, raw)

    # ------------------------------------------------------------------
    # Vacuum -- commands (gated)
    # ------------------------------------------------------------------
    async def start(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_vacuum(device_id, VacuumCommand.START)

    async def stop(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_vacuum(device_id, VacuumCommand.STOP)

    async def pause(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_vacuum(device_id, VacuumCommand.PAUSE)

    async def return_to_base(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send_vacuum(device_id, VacuumCommand.RETURN_TO_BASE)

    async def _send_vacuum(self, device_id: str, command: VacuumCommand) -> dict[str, Any]:
        device = await self._require_vacuum(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _VACUUM_TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Vacuum control has no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}

    # ------------------------------------------------------------------
    # Humidifier -- reads (ungated -- Logic Contract §13)
    # ------------------------------------------------------------------
    async def list_humidifiers(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        humidifier."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_humidifier_payload(d) for d in devices if _domain_for(d) == _HUMIDIFIER_DOMAIN]

    async def get_humidifier_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_humidifier(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _humidifier_payload(device, raw)

    # ------------------------------------------------------------------
    # Humidifier -- command (gated)
    # ------------------------------------------------------------------
    async def set_humidifier_state(
        self,
        device_id: str,
        *,
        on: bool | None = None,
        target_humidity: float | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        if on is None and target_humidity is None:
            raise ServiceError(
                "set_humidifier_state requires at least one of 'on' or 'target_humidity'."
            )

        device = await self._require_humidifier(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _HUMIDIFIER_TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Humidifier control has no command translation for connector type "
                f"{connector_type!r}."
            )

        validated_humidity = (
            None if target_humidity is None else _validate_target_humidity(target_humidity)
        )
        if validated_humidity is not None:
            await self._check_humidity_bounds(device_id, validated_humidity)

        calls = translator(on=on, target_humidity=validated_humidity)
        return await self._send_all(device_id, calls)

    async def _check_humidity_bounds(self, device_id: str, target_humidity: float) -> None:
        """Enforces **only** the device's own reported `min_humidity`/
        `max_humidity` -- no invented default range (Logic Contract
        §8, reusing `ThermostatService`'s identical rule). A read
        failure here is never fatal to the mutation."""
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        attributes = raw.attributes or {}
        minimum = _coerce_float(attributes.get("min_humidity"))
        maximum = _coerce_float(attributes.get("max_humidity"))
        if minimum is not None and target_humidity < minimum:
            raise ServiceError(
                f"target_humidity {target_humidity} is below this device's reported "
                f"minimum {minimum}."
            )
        if maximum is not None and target_humidity > maximum:
            raise ServiceError(
                f"target_humidity {target_humidity} is above this device's reported "
                f"maximum {maximum}."
            )

    async def _send_all(
        self, device_id: str, calls: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        """Executes each wire call in order, stopping at the first
        failure. A partially-applied combined update reports
        `success=False` naming exactly what did and did not apply --
        never a full success, never a silent retry."""
        applied: list[str] = []
        for command, payload in calls:
            result = await self._connectivity.send_command(device_id, command, payload)
            if not result.success:
                detail = result.detail
                if applied:
                    detail = (
                        f"{command} failed ({detail or 'no detail'}); "
                        f"already applied: {', '.join(applied)}."
                    )
                return {"device_id": device_id, "success": False, "detail": detail}
            applied.append(command)
        return {"device_id": device_id, "success": True, "detail": ""}
