"""Water Heater service -- Milestone 12 Appliance Control (Water Heater
Core Slice).

**Deliberately not an `ApplianceService` extension.** `ApplianceService`'s
own module docstring already establishes the rule this module follows:
"a future appliance category (climate, media_player, vacuum,
water_heater, humidifier) gets its own Logic Contract and, per that
contract, likely its own service -- not a new branch bolted onto this
one" (`appliance_service.py:19-20`). `water_heater` shares
`device_type="appliance"` with Fan/Cover/Vacuum/Humidifier/Media
Player (unlike Climate's own `device_type`), so this module mirrors
`VacuumHumidifierService`'s/`MediaPlayerService`'s domain-
discrimination shape.

**The MQTT `component`/`domain` fallback is local to this module.**
`MqttConnector._handle_ha_discovery` writes `metadata["component"]`,
never `metadata["domain"]` -- the same pre-existing gap Vacuum +
Humidifier first worked around and Media Player reused verbatim. This
module's own `_domain_for` checks `metadata["domain"]` first, falling
back to `metadata["component"]` -- `ApplianceService`'s own identical
gap was fixed separately (M0-M12 Structured Rework Audit, P1-1), not
touched here.

**Operation mode is writable, validated against the device's own
reported `operation_list`** -- HA's real `water_heater.
set_operation_mode` service (verified against HA's actual
`services.yaml` this session) takes exactly one field,
`operation_mode`, matching `ThermostatService`'s `hvac_mode`/
`hvac_modes` template rather than Humidifier's read-only `mode`.

**Temperature stays whatever unit/precision the device reports -- no
conversion, no invented safety limit.** Bounds are enforced only when
the device itself reports `min_temp`/`max_temp`
(`docs/M12_APPLIANCE_WATER_HEATER_LOGIC_CONTRACT.md` §5).

**Three independent, single-purpose HA services** (`turn_on`/
`turn_off`, `set_operation_mode`, `set_temperature`), verified against
HA's actual `services.yaml` this session -- a combined update is up to
three sequential calls, ordered on/off, then mode, then temperature (a
stated convention, not a discovered HA dependency -- Logic Contract
§10). MQTT's own envelope has no such constraint and stays one merged
`set_state` call.
"""

from __future__ import annotations

import contextlib
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
#: against -- one principal covering the whole module, mirroring
#: `MEDIA_PLAYER_PRINCIPAL`'s naming and one-principal-per-module
#: reasoning.
WATER_HEATER_PRINCIPAL = "core:water_heaters"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

_APPLIANCE_DEVICE_TYPE = "appliance"
_WATER_HEATER_DOMAIN = "water_heater"

_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})
_ON_VALUES = frozenset({"on", "true", "1"})
_OFF_VALUES = frozenset({"off", "false", "0"})


def _translate_state_home_assistant(
    *, on: bool | None, operation_mode: str | None, temperature: float | None
) -> list[tuple[str, dict[str, Any]]]:
    """HA's own three independent single-purpose services -- `turn_on`/
    `turn_off`, `set_operation_mode`, `set_temperature` -- verified
    against HA's actual `services.yaml` this session (Logic Contract
    §8/§20's evidence ledger): `set_operation_mode` takes exactly
    `{"operation_mode": <str>}`; `set_temperature` takes
    `{"temperature": <float>}` (it also optionally accepts
    `operation_mode`, but this module never uses that combined form --
    the contract's own three-independent-calls design is retained
    deliberately, not silently replaced by a discovered shortcut).
    **Up to three calls when all three are requested**, in the
    contract's declared order (on/off, mode, temperature) -- a
    convention, not a discovered HA dependency, since no evidence ties
    operation mode to what a temperature setpoint means the way
    Thermostat's HVAC mode does."""
    calls: list[tuple[str, dict[str, Any]]] = []
    if on is True:
        calls.append(("turn_on", {}))
    elif on is False:
        calls.append(("turn_off", {}))
    if operation_mode is not None:
        calls.append(("set_operation_mode", {"operation_mode": operation_mode}))
    if temperature is not None:
        calls.append(("set_temperature", {"temperature": temperature}))
    return calls


def _translate_state_mqtt(
    *, on: bool | None, operation_mode: str | None, temperature: float | None
) -> list[tuple[str, dict[str, Any]]]:
    """The JARVIS-native MQTT vocabulary this module defines -- always
    one merged `set_state` call, mirroring `ThermostatService`'s/
    `VacuumHumidifierService`'s/`MediaPlayerService`'s own MQTT
    convention. Deliberately *not* copying HA's three-service split --
    the MQTT envelope has no such constraint."""
    args: dict[str, Any] = {}
    if on is not None:
        args["on"] = on
    if operation_mode is not None:
        args["operation_mode"] = operation_mode
    if temperature is not None:
        args["temperature"] = temperature
    return [("set_state", args)]


_STATE_TRANSLATORS = {
    "home_assistant": _translate_state_home_assistant,
    "mqtt": _translate_state_mqtt,
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
    Contract §2. Local to this module by design; not shared with
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


def _coerce_operation_list(value: Any) -> list[str]:
    """The device's own reported supported-operation-mode list,
    normalized to stripped lowercase strings. `[]` when unreported or
    not a list -- never a fabricated default vocabulary. Case is
    lowercased (unlike Media Player's `source_list`), mirroring
    `ThermostatService._coerce_modes`: operation modes are short,
    enum-like tokens (`eco`/`electric`/`gas`/...), not human-facing
    mixed-case labels (Logic Contract §6)."""
    if not isinstance(value, (list, tuple)):
        return []
    modes: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            modes.append(entry.strip().lower())
    return modes


def _infer_on(status: str) -> bool | None:
    """`True`/`False` when the lowercased state string is a recognized
    on/off token, `None` otherwise -- including when the state is an
    operation-mode token like `"eco"`, since an operation mode being
    reported does not by itself prove the device is powered on (Logic
    Contract §7)."""
    normalized = status.strip().lower()
    if normalized in _ON_VALUES:
        return True
    if normalized in _OFF_VALUES:
        return False
    return None


def _validate_temperature(value: Any) -> float:
    """Rejects `bool`, non-numerics, NaN and +/-inf. Imposes **no**
    range of its own -- device-reported `min_temp`/`max_temp` are the
    only bounds ever enforced (see `_check_bounds`); HA's own
    `set_temperature` service UI selector advertises a generous
    0-250 range, which is a form-widget convenience, not a protocol-
    level or device-safety constraint, so it is deliberately not
    encoded here (Logic Contract §5/§18 Risk 4)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(f"temperature must be a number; got {value!r}.")
    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ServiceError(f"temperature must be a finite number; got {value!r}.")
    return parsed


def _validate_operation_mode(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ServiceError(f"operation_mode must be a non-empty string; got {value!r}.")
    return value.strip().lower()


def _validate_on(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ServiceError(f"on must be a boolean; got {value!r}.")
    return value


def _water_heater_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "is_on": None,
        "available": False,
        "current_temperature": None,
        "target_temperature": None,
        "operation_mode": None,
        "operation_list": [],
        "min_temp": None,
        "max_temp": None,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    attributes = raw.attributes or {}
    # Capability fields survive unavailability -- they describe the
    # device's declared range/mode list, not a live reading (mirrors
    # ThermostatService's identical rule for hvac_modes/min_temp/max_temp).
    payload["operation_list"] = _coerce_operation_list(attributes.get("operation_list"))
    payload["min_temp"] = _coerce_float(attributes.get("min_temp"))
    payload["max_temp"] = _coerce_float(attributes.get("max_temp"))
    if payload["available"]:
        # Open pass-through -- the entity's own state string can be
        # either a plain on/off token or an operation-mode token
        # depending on which features a real integration supports
        # (Logic Contract §7); never validated against a closed
        # vocabulary, and never the literal "unavailable"/"offline"
        # string once forced None above.
        normalized = raw.status.strip().lower()
        payload["state"] = normalized or None
        payload["is_on"] = _infer_on(raw.status) if payload["state"] is not None else None
        payload["operation_mode"] = payload["state"]
        payload["current_temperature"] = _coerce_float(attributes.get("current_temperature"))
        payload["target_temperature"] = _coerce_float(attributes.get("temperature"))
    return payload


class WaterHeaterService:
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
        self._permissions.declare(WATER_HEATER_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(WATER_HEATER_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Water Heater control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{WATER_HEATER_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{WATER_HEATER_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Domain discrimination
    # ------------------------------------------------------------------
    async def _require_water_heater(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if (
            device.device_type != _APPLIANCE_DEVICE_TYPE
            or _domain_for(device) != _WATER_HEATER_DOMAIN
        ):
            raise ServiceError(f"Device {device_id!r} is not a water heater.")
        return device

    # ------------------------------------------------------------------
    # Reads (ungated -- Logic Contract §11)
    # ------------------------------------------------------------------
    async def list_water_heaters(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        device, the same list/detail asymmetry every prior M12 module
        draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_APPLIANCE_DEVICE_TYPE
        )
        return [_water_heater_payload(d) for d in devices if _domain_for(d) == _WATER_HEATER_DOMAIN]

    async def get_water_heater_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_water_heater(device_id)
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _water_heater_payload(device, raw)

    # ------------------------------------------------------------------
    # Merged state mutation (gated)
    # ------------------------------------------------------------------
    async def set_water_heater_state(
        self,
        device_id: str,
        *,
        temperature: float | None = None,
        operation_mode: str | None = None,
        on: bool | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        if temperature is None and operation_mode is None and on is None:
            raise ServiceError(
                "set_water_heater_state requires at least one of 'temperature', "
                "'operation_mode', or 'on'."
            )

        device = await self._require_water_heater(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _STATE_TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Water Heater has no command translation for connector type " f"{connector_type!r}."
            )

        validated_on = None if on is None else _validate_on(on)
        validated_mode = (
            None if operation_mode is None else _validate_operation_mode(operation_mode)
        )
        validated_temperature = None if temperature is None else _validate_temperature(temperature)
        if validated_mode is not None:
            await self._check_operation_mode(device_id, validated_mode)
        if validated_temperature is not None:
            await self._check_temperature_bounds(device_id, validated_temperature)

        calls = translator(
            on=validated_on, operation_mode=validated_mode, temperature=validated_temperature
        )
        return await self._send_all(device_id, calls)

    async def _check_operation_mode(self, device_id: str, operation_mode: str) -> None:
        """Validates a requested mode against the device's **own**
        reported `operation_list`. Permissive when the device reports
        none -- rejecting a real device over a vocabulary gap is the
        worse failure (`DEVICE_TYPES`' own stated principle), and no
        fixed operation-mode enum is invented here (Logic Contract
        §6)."""
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        supported = _coerce_operation_list((raw.attributes or {}).get("operation_list"))
        if supported and operation_mode not in supported:
            raise ServiceError(
                f"operation_mode {operation_mode!r} is not supported by this device; "
                f"it reports {sorted(supported)}."
            )

    async def _check_temperature_bounds(self, device_id: str, temperature: float) -> None:
        """Enforces **only** the device's own reported `min_temp`/
        `max_temp` -- no invented default range (Logic Contract §5,
        reusing `ThermostatService`'s identical rule). A read failure
        here is never fatal to the mutation."""
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        attributes = raw.attributes or {}
        minimum = _coerce_float(attributes.get("min_temp"))
        maximum = _coerce_float(attributes.get("max_temp"))
        if minimum is not None and temperature < minimum:
            raise ServiceError(
                f"temperature {temperature} is below this device's reported minimum {minimum}."
            )
        if maximum is not None and temperature > maximum:
            raise ServiceError(
                f"temperature {temperature} is above this device's reported maximum {maximum}."
            )

    async def _send_all(
        self, device_id: str, calls: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        """Executes each wire call in order, stopping at the first
        failure. A partially-applied combined update reports
        `success=False` naming exactly what did and did not apply --
        never a full success, never a silent retry, never claimed
        atomic (Logic Contract §10)."""
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
