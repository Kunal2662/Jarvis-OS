"""Siren service -- Milestone 12 Security & Safety (Siren Integration
Slice).

The first M12 device-category service to discriminate a device living
inside the generic `device_type="other"` bucket rather than its own
dedicated `device_type` or the shared `"appliance"` bucket -- see
`docs/M12_SECURITY_SIREN_INTEGRATION_LOGIC_CONTRACT.md` §4. Both
connectors already capture a discovered entity's own HA domain (or
MQTT Discovery component) into `metadata["domain"]`/`["component"]`
**unconditionally, for every device, regardless of `device_type`** --
confirmed by direct trace of `home_assistant.py:_entity_to_discovered_
device` and `mqtt.py:_handle_ha_discovery` this contract's own Phase 1
investigation performed. A siren is therefore already fully
identifiable today, with zero connector or `DEVICE_TYPES` change --
this module only adds the read/write service that acts on that
already-captured identity, the same "domain"/"component" fallback
order every appliance-domain service (`VacuumHumidifierService`,
`MediaPlayerService`, `WaterHeaterService`) already establishes for
`device_type="appliance"`, applied here to `device_type="other"` for
the first time.

**Deliberately its own sibling service, not an extension of
`SmartSwitchService` or `SecurityService`.** `SmartSwitchService` is
hard-scoped to `device_type="switch"` -- a siren is a structurally
different HA domain reached through a different entity domain, not a
switch. `SecurityService.trigger_panic_mode`'s own docstring already
states it *"never touches thermostats/cameras/sirens"* -- extending
that class would contradict its own documented, tested boundary. A
siren is a new device category by the same test every other M12
appliance-domain service already passed (Logic Contract §3).

**Two separate mutations, `turn_on`/`turn_off`, never a merged
`set_siren_state`.** This is not stylistic: `turn_on` alone is
confirmation-gated (`AgentSettings.confirm_required_tools`), `turn_off`
is not -- the same directional-risk asymmetry `SmartLockService.lock`/
`.unlock` already established (locking needs no confirmation,
unlocking does). A merged mutation would force confirming both
directions or duplicate a per-argument confirmation mechanism this
codebase has no precedent for (Logic Contract §7/§10).

**Home Assistant's own `siren.turn_on`/`turn_off` services take an
entirely optional payload** (`tone`/`duration`/`volume_level`, each
gated behind its own `SirenEntityFeature` flag, verified against Home
Assistant's own developer documentation during the Logic Contract's
own Phase 1) -- a bare call with no payload is a complete, valid
command for any siren regardless of which optional features it
supports. This MVP sends no payload at all.
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
#: against -- one fixed principal, mirroring every other M12 module's
#: naming.
SIREN_PRINCIPAL = "core:sirens"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

#: Sirens are discovered under the generic `device_type="other"`
#: bucket -- both connectors already map HA's own `siren` domain (and
#: MQTT Discovery's own `siren` component) there, since neither
#: reserves a dedicated `device_type` for it (`domain/smart_home/
#: models.py`'s own closed vocabulary). Discrimination within this
#: bucket happens entirely in this module, via `_domain_for` below --
#: `DEVICE_TYPES`/`CONNECTOR_TYPES`/either connector are unmodified.
_OTHER_DEVICE_TYPE = "other"

#: The HA domain / MQTT Discovery component name identifying a siren.
_SIREN_DOMAIN = "siren"


class SirenCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"


def _translate_home_assistant(command: SirenCommand) -> tuple[str, dict[str, Any]]:
    """HA's own siren-domain service names, no payload -- `siren.
    turn_on`'s own `tone`/`duration`/`volume_level` parameters are all
    optional and gated behind device-specific `SirenEntityFeature`
    flags (verified against Home Assistant's own developer
    documentation), so a bare call is a complete, valid command for
    any siren regardless of which optional features it reports."""
    return command.value, {}


def _translate_mqtt(command: SirenCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines, deliberately
    mirroring HA's own siren-domain service names for cross-connector
    predictability -- the same choice `smart_switch_service.py`'s own
    `_translate_mqtt` and `smart_lock_service.py`'s own made for their
    respective command vocabularies."""
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


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _domain_for(device: Device) -> str | None:
    """`metadata["domain"]` (HA-sourced discovery), falling back to
    `metadata["component"]` (MQTT-native discovery) -- the same
    fallback order every `device_type="appliance"` service already
    uses, applied here to `device_type="other"` for the first time
    (Logic Contract §4)."""
    meta = _metadata(device)
    domain = meta.get("domain")
    if domain:
        return str(domain)
    component = meta.get("component")
    return str(component) if component else None


def _siren_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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


class SirenService:
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
        self._permissions.declare(SIREN_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SIREN_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Siren control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SIREN_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SIREN_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads (ungated -- see module docstring / Logic Contract §9)
    # ------------------------------------------------------------------
    async def _require_siren(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _OTHER_DEVICE_TYPE or _domain_for(device) != _SIREN_DOMAIN:
            raise ServiceError(f"Device {device_id!r} is not a siren.")
        return device

    async def list_sirens(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        siren, the same list/detail asymmetry every prior M12 module
        draws. `device_type="other"` is a large, heterogeneous bucket
        (also `select`/`number`/`valve`/`alarm_control_panel`/anything
        unmapped) -- this method lists every such device, then filters
        to sirens in Python, the same "list, then Python-filter by
        metadata" tradeoff `VacuumHumidifierService`/`MediaPlayerService`
        already accept for their own, smaller `"appliance"` bucket."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_OTHER_DEVICE_TYPE
        )
        return [_siren_payload(d) for d in devices if _domain_for(d) == _SIREN_DOMAIN]

    async def get_siren_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_siren(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state rather than fail the read; mirrors every prior M12
        # device-category service's own `get_X_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _siren_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def turn_on(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, SirenCommand.TURN_ON)

    async def turn_off(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, SirenCommand.TURN_OFF)

    async def _send(self, device_id: str, command: SirenCommand) -> dict[str, Any]:
        device = await self._require_siren(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Siren control has no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}
