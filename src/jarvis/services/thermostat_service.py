"""Thermostat service -- Milestone 12 Appliance Control (Climate /
Thermostat Slice).

The first module to use ``device_type="thermostat"`` -- Task Group A's
own ``DEVICE_TYPES`` already reserved it (``domain/smart_home/
models.py``) precisely for this. **Deliberately not an extension of
``ApplianceService``**: a thermostat is its own device type, not a
``device_type="appliance"`` device distinguished by
``metadata["domain"]`` the way a fan and a cover are, so it needs no
domain discrimination at all -- ``_require_thermostat`` checks
``device_type`` and nothing else, exactly like ``SmartLightingService.
_require_light``.

**Multi-attribute, like Smart Lighting -- unlike Locks/Switches/
Appliances.** ``set_thermostat_state`` takes both attributes as
optional keywords and translates to the fewest wire calls the target
connector supports, mirroring ``smart_lighting_service.py``'s own
"merge whatever is set into one wire command" shape.

**Two connectors, two genuinely different wire shapes.** Home Assistant
models climate control as two distinct services (``climate.
set_hvac_mode`` / ``climate.set_temperature``), so a combined update is
two sequential calls there -- the Logic Contract's documented fallback,
selected because the repository carries no evidence that HA's
``set_temperature`` accepts an optional ``hvac_mode`` field (searched
this session: zero references to ``set_temperature``/``hvac_mode``
anywhere in ``src/`` or ``tests/`` before this module). MQTT's own
envelope has no such constraint, so it stays one merged ``set_state``
call. Translators therefore return a *list* of wire calls, not one --
the one structural difference from Smart Lighting's own translators.

**Partial failure is reported, never hidden.** When a combined HA
update applies the mode but fails the temperature, the result is
``success=False`` with a detail naming exactly what did and did not
apply -- never a full success, and never a silent retry.

**Permission**: reads are ungated (following Smart Lighting/Smart
Locks/Smart Switches/Appliance Control -- a setpoint carries no
Sensors-grade privacy weight); mutations require the existing
``smart_home`` scope under a new principal, ``core:thermostats``.
"""

from __future__ import annotations

import contextlib
import enum
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
#: against -- one fixed principal, mirroring `SMART_LIGHTING_PRINCIPAL`/
#: `APPLIANCE_PRINCIPAL`'s exact naming and reasoning.
THERMOSTAT_PRINCIPAL = "core:thermostats"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

#: Task Group A's own closed `DEVICE_TYPES` vocabulary
#: (`domain/smart_home/models.py`) -- already contains "thermostat".
_THERMOSTAT_DEVICE_TYPE = "thermostat"

#: A connector's raw status string meaning "this device is down".
#: Mirrors (does not import) the same small module-local heuristic every
#: prior M12 module defines for itself. Deliberately the same two values
#: Sensors/Locks/Switches/Appliances already use -- "unknown" is *not*
#: included, matching Sensors' own explicit precedent that "unknown" is
#: unparseable-but-reachable, not offline.
_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})


class ThermostatCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports -- used in
    docstrings and by callers that want to know what a thermostat
    command *is*. Like `LightCommand`, it is not the translators' own
    dispatch key; translation works on keyword attributes."""

    SET_TEMPERATURE = "set_temperature"
    SET_HVAC_MODE = "set_hvac_mode"


def _translate_home_assistant(
    *, temperature: float | None, hvac_mode: str | None
) -> list[tuple[str, dict[str, Any]]]:
    """HA's own climate-domain service names, reached through the
    existing generic dispatcher (`HomeAssistantConnector.send_command`
    derives `domain` from `external_id.split(".", 1)[0]`, so a
    `climate.*` entity routes to `POST /api/services/climate/{command}`
    -- verified against the shipped connector this session, no
    connector change needed).

    **Two calls for a combined update**, mode first so the setpoint
    applies to the intended mode. This is the Logic Contract's §8b
    fallback, chosen because no repository evidence confirms HA's
    `set_temperature` accepts an optional `hvac_mode` field; the
    contract forbids inventing a third approach.
    """
    calls: list[tuple[str, dict[str, Any]]] = []
    if hvac_mode is not None:
        calls.append((ThermostatCommand.SET_HVAC_MODE.value, {"hvac_mode": hvac_mode}))
    if temperature is not None:
        calls.append((ThermostatCommand.SET_TEMPERATURE.value, {"temperature": temperature}))
    return calls


def _translate_mqtt(
    *, temperature: float | None, hvac_mode: str | None
) -> list[tuple[str, dict[str, Any]]]:
    """The JARVIS-native MQTT climate vocabulary this module defines --
    `mqtt_envelope.build_command_envelope` leaves command/args
    deliberately free-form and no climate consumer existed before this
    module, so this is a first definition, not a guess at an existing
    one (the same situation Lighting/Locks/Switches/Appliances each had).

    **Always one merged call**, mirroring Lighting's own MQTT
    `set_state` -- deliberately *not* copying HA's two-service split,
    because the MQTT envelope has no such constraint and a single
    message applies atomically.
    """
    args: dict[str, Any] = {}
    if temperature is not None:
        args["temperature"] = temperature
    if hvac_mode is not None:
        args["hvac_mode"] = hvac_mode
    return [("set_state", args)]


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _coerce_float(value: Any) -> float | None:
    """`None` for anything unparseable -- never a silently wrong `0.0`,
    the same rule `SensorService._parse_numeric` already enforces.
    `bool` is rejected explicitly: it is an `int` subclass, so a bare
    `float()` would silently turn `True` into `1.0`."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(parsed) or math.isinf(parsed) else parsed


def _coerce_modes(value: Any) -> list[str]:
    """The device's own reported supported-mode list, normalized to
    stripped lowercase strings. `[]` when unreported or not a list --
    never a fabricated default vocabulary."""
    if not isinstance(value, (list, tuple)):
        return []
    modes: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            modes.append(entry.strip().lower())
    return modes


def _normalize_mode(value: str) -> str:
    return value.strip().lower()


def _validate_temperature(value: Any) -> float:
    """Rejects `bool`, non-numerics, NaN and +/-inf. Imposes **no**
    range of its own -- device-reported `min_temp`/`max_temp` are the
    only bounds ever enforced (see `_check_bounds`), and no safety
    limit is invented where the device reports none."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ServiceError(f"temperature must be a number; got {value!r}.")
    parsed = float(value)
    if math.isnan(parsed) or math.isinf(parsed):
        raise ServiceError(f"temperature must be a finite number; got {value!r}.")
    return parsed


def _thermostat_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "current_temperature": None,
        "target_temperature": None,
        "hvac_mode": None,
        "hvac_modes": [],
        "min_temp": None,
        "max_temp": None,
        "available": False,
    }
    if raw is None:
        return payload

    payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
    attributes = raw.attributes or {}
    # Reported even when unavailable -- a device's declared capability
    # range and supported modes remain true regardless of current
    # reachability, unlike the live readings below.
    payload["hvac_modes"] = _coerce_modes(attributes.get("hvac_modes"))
    payload["min_temp"] = _coerce_float(attributes.get("min_temp"))
    payload["max_temp"] = _coerce_float(attributes.get("max_temp"))
    if payload["available"]:
        # For an HA climate entity the entity's own state string *is*
        # the HVAC mode -- so an unavailable device must never have
        # "unavailable"/"offline" recorded as its mode. That is why this
        # read is gated on availability while the two above are not.
        payload["hvac_mode"] = _normalize_mode(raw.status) or None
        payload["current_temperature"] = _coerce_float(attributes.get("current_temperature"))
        payload["target_temperature"] = _coerce_float(attributes.get("temperature"))
    return payload


class ThermostatService:
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
        self._permissions.declare(THERMOSTAT_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Thermostat control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{THERMOSTAT_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{THERMOSTAT_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads (ungated -- see module docstring / Logic Contract §10)
    # ------------------------------------------------------------------
    async def _require_thermostat(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _THERMOSTAT_DEVICE_TYPE:
            raise ServiceError(
                f"Device {device_id!r} is a {device.device_type!r}, not a thermostat."
            )
        return device

    async def list_thermostats(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        thermostat, the same list/detail asymmetry every prior M12
        module draws."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_THERMOSTAT_DEVICE_TYPE
        )
        return [_thermostat_payload(d) for d in devices]

    async def get_thermostat_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_thermostat(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # fields (live values None, available=False) rather than fail
        # the read; mirrors `SmartLightingService.get_light_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _thermostat_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def set_thermostat_state(
        self,
        device_id: str,
        *,
        temperature: float | None = None,
        hvac_mode: str | None = None,
    ) -> dict[str, Any]:
        self._require_permission()
        if temperature is None and hvac_mode is None:
            raise ServiceError(
                "set_thermostat_state requires at least one of 'temperature' or 'hvac_mode'."
            )

        device = await self._require_thermostat(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Thermostats have no command translation for connector type {connector_type!r}."
            )

        validated_temperature = None if temperature is None else _validate_temperature(temperature)
        validated_mode = None if hvac_mode is None else self._validate_mode(hvac_mode)
        await self._validate_against_device(
            device_id, temperature=validated_temperature, hvac_mode=validated_mode
        )

        calls = translator(temperature=validated_temperature, hvac_mode=validated_mode)
        return await self._send_all(device_id, calls)

    def _validate_mode(self, hvac_mode: Any) -> str:
        if not isinstance(hvac_mode, str) or not hvac_mode.strip():
            raise ServiceError(f"hvac_mode must be a non-empty string; got {hvac_mode!r}.")
        return _normalize_mode(hvac_mode)

    async def _validate_against_device(
        self, device_id: str, *, temperature: float | None, hvac_mode: str | None
    ) -> None:
        """Validates the request against the device's **own** declared
        capabilities -- reported `min_temp`/`max_temp` bounds and
        reported `hvac_modes`. One live read serves both checks.

        Permissive by design where the device declares nothing: no
        safety limit is invented where no `min_temp`/`max_temp` is
        reported (Logic Contract §7), and no fixed HVAC enum is
        invented where no `hvac_modes` is reported -- rejecting a real
        device over a vocabulary gap is the worse failure
        (`DEVICE_TYPES`' own stated principle). An unreadable device
        simply has no declarations to check against, so the mutation
        proceeds and the connector remains the authority.
        """
        raw = None
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        if raw is None:
            return
        attributes = raw.attributes or {}

        if temperature is not None:
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

        if hvac_mode is not None:
            supported = _coerce_modes(attributes.get("hvac_modes"))
            if supported and hvac_mode not in supported:
                raise ServiceError(
                    f"hvac_mode {hvac_mode!r} is not supported by this device; "
                    f"it reports {sorted(supported)}."
                )

    async def _send_all(
        self, device_id: str, calls: list[tuple[str, dict[str, Any]]]
    ) -> dict[str, Any]:
        """Executes each wire call in order, stopping at the first
        failure. A partially-applied combined update reports
        `success=False` naming exactly what did and did not apply --
        never a full success, and never a silent retry (Logic Contract
        §11)."""
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
