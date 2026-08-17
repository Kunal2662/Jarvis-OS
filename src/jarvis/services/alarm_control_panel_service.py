"""Alarm control panel service -- Milestone 12 Security & Safety
(alarm_control_panel Integration Slice).

A second M12 device-category service to discriminate a device living
inside the generic `device_type="other"` bucket rather than its own
dedicated `device_type` or the shared `"appliance"` bucket -- see
`docs/M12_SECURITY_ALARM_CONTROL_PANEL_LOGIC_CONTRACT.md` §4. Both
connectors already map `"alarm_control_panel": "other"` in their own
domain tables (byte-identical in shape to `"siren": "other"` on the
line directly above each) -- confirmed by direct trace of
`home_assistant.py`/`mqtt.py` this contract's own Phase 1 investigation
performed. An alarm control panel is therefore already fully
identifiable today, with zero connector or `DEVICE_TYPES` change --
this module only adds the read/write service that acts on that
already-captured identity, reusing `SirenService`'s own `domain`/
`component` fallback order verbatim.

**Deliberately its own sibling service, not an extension of
`SecurityService` or `SirenService`.** `SecurityService.
trigger_panic_mode`'s own docstring already states it *"never touches
thermostats/cameras/sirens"* -- extending that class would contradict
its own documented, tested boundary, the identical reasoning that
already ruled out extending it for Siren. An alarm control panel is a
structurally different HA domain from a siren, reached through its
own entity domain, not a variant of one.

**Exactly three mutations -- `arm_home`/`arm_away`/`disarm` -- never
`arm_night`/`arm_vacation`/`arm_custom_bypass`/`trigger`.** Home
Assistant's own `AlarmControlPanelState` enum has ten real values and
seven real arm/disarm/trigger services (externally verified against
Home Assistant's own current developer documentation during the Logic
Contract's own Phase 1); this MVP deliberately covers only the two
most universal arm modes plus disarm, deferring the rest as narrower
variants of an already-proven mechanism (Logic Contract §21).

**No PIN/code parameter exists anywhere in this module, permanently --
not a deferred gap.** Home Assistant's own service documentation
offers zero security guidance on storing, logging, or transmitting an
alarm code, and its own MQTT alarm integration explicitly warns that
an unprotected MQTT connection sends a secret code over the network in
the clear (both externally verified during the Logic Contract's own
Phase 1). Every action this module sends is a bare, zero-payload
command -- Home Assistant's own documentation confirms this is a
complete, valid call for any panel that does not require a code; a
code-protected panel simply reports the action failed, honestly, via
the same `CommandResult` path every other M12 mutation already uses.
No method, request body, tool argument, or wire payload in this module
has a parameter that could carry a code -- the absence is structural,
not a runtime redaction.

**Same directional-risk asymmetry `SmartLockService.lock`/`.unlock`
and `SirenService.turn_on`/`.turn_off` already established.** Arming
(either mode) adds protection and is never confirmation-gated;
disarming removes protection and is confirmation-gated
(`AgentSettings.confirm_required_tools`) -- see Logic Contract §12.
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
ALARM_CONTROL_PANEL_PRINCIPAL = "core:alarm_control_panels"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

#: Alarm control panels are discovered under the generic
#: `device_type="other"` bucket -- both connectors already map HA's
#: own `alarm_control_panel` domain there, since neither reserves a
#: dedicated `device_type` for it (`domain/smart_home/models.py`'s own
#: closed vocabulary). Discrimination within this bucket happens
#: entirely in this module, via `_domain_for` below --
#: `DEVICE_TYPES`/`CONNECTOR_TYPES`/either connector are unmodified.
_OTHER_DEVICE_TYPE = "other"

#: The HA domain / MQTT Discovery component name identifying an alarm
#: control panel.
_ALARM_CONTROL_PANEL_DOMAIN = "alarm_control_panel"

#: Home Assistant's own `AlarmControlPanelState` vocabulary, externally
#: verified against Home Assistant's own current developer
#: documentation (Logic Contract §5) -- anything else (including an
#: empty/unrecognized string) reports `state=None` rather than
#: fabricating a value the connector layer itself does not represent,
#: the same "detect at use, not fabricate" discipline
#: `ApplianceService._infer_cover_state` already applies.
_ALARM_STATE_VALUES = frozenset(
    {
        "disarmed",
        "armed_home",
        "armed_away",
        "armed_night",
        "armed_vacation",
        "armed_custom_bypass",
        "pending",
        "arming",
        "disarming",
        "triggered",
    }
)

_OFFLINE_STATUS_VALUES = frozenset({"offline", "unavailable"})


class AlarmControlPanelCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports -- see
    module docstring for why `arm_night`/`arm_vacation`/
    `arm_custom_bypass`/`trigger` are deliberately absent."""

    ARM_HOME = "arm_home"
    ARM_AWAY = "arm_away"
    DISARM = "disarm"


def _translate_home_assistant(
    command: AlarmControlPanelCommand,
) -> tuple[str, dict[str, Any]]:
    """HA's own alarm_control_panel-domain service names
    (`alarm_arm_home`/`alarm_arm_away`/`alarm_disarm`), no payload --
    verified directly against the shipped `HomeAssistantConnector.
    send_command` this session (domain/service split from `entity_id`,
    body = `{"entity_id": ..., **payload}`). Deliberately no `code`
    field is ever placed in this payload (Logic Contract §8)."""
    _wire_service = {
        AlarmControlPanelCommand.ARM_HOME: "alarm_arm_home",
        AlarmControlPanelCommand.ARM_AWAY: "alarm_arm_away",
        AlarmControlPanelCommand.DISARM: "alarm_disarm",
    }
    return _wire_service[command], {}


def _translate_mqtt(command: AlarmControlPanelCommand) -> tuple[str, dict[str, Any]]:
    """A JARVIS-native vocabulary this module defines, deliberately
    mirroring HA's own normalized command names for cross-connector
    predictability -- the same choice `siren_service.py`'s own
    `_translate_mqtt` already made. Verified against the shipped
    `MqttConnector.send_command`/`build_command_envelope` this
    session. No `code` field, ever (Logic Contract §8/§9)."""
    return command.value, {}


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _metadata(device: Device) -> dict[str, Any]:
    try:
        parsed = json.loads(device.metadata_json or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _domain_for(device: Device) -> str | None:
    """`metadata["domain"]` (HA-sourced discovery), falling back to
    `metadata["component"]` (MQTT-native discovery) -- the same
    fallback order `SirenService._domain_for` already establishes for
    `device_type="other"`, reused verbatim (Logic Contract §4)."""
    meta = _metadata(device)
    domain = meta.get("domain")
    if domain:
        return str(domain)
    component = meta.get("component")
    return str(component) if component else None


def _infer_state(status: str) -> str | None:
    normalized = status.strip().lower()
    return normalized if normalized in _ALARM_STATE_VALUES else None


def _alarm_control_panel_payload(device: Device, raw: Any = None) -> dict[str, Any]:
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
        "available": raw is not None,
    }
    if raw is not None:
        payload["available"] = raw.status.strip().lower() not in _OFFLINE_STATUS_VALUES
        if payload["available"]:
            payload["state"] = _infer_state(raw.status)
    return payload


class AlarmControlPanelService:
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
        self._permissions.declare(ALARM_CONTROL_PANEL_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(ALARM_CONTROL_PANEL_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Alarm control panel control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{ALARM_CONTROL_PANEL_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{ALARM_CONTROL_PANEL_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads (ungated -- see module docstring / Logic Contract §15)
    # ------------------------------------------------------------------
    async def _require_alarm_control_panel(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if (
            device.device_type != _OTHER_DEVICE_TYPE
            or _domain_for(device) != _ALARM_CONTROL_PANEL_DOMAIN
        ):
            raise ServiceError(f"Device {device_id!r} is not an alarm control panel.")
        return device

    async def list_alarm_control_panels(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        panel, the same list/detail asymmetry every prior M12 module
        draws. `device_type="other"` is a large, heterogeneous bucket
        -- this method lists every such device, then filters to alarm
        control panels in Python, the same "list, then Python-filter
        by metadata" tradeoff `SirenService.list_sirens` already
        accepts for its own, larger `"other"` bucket."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_OTHER_DEVICE_TYPE
        )
        return [
            _alarm_control_panel_payload(d)
            for d in devices
            if _domain_for(d) == _ALARM_CONTROL_PANEL_DOMAIN
        ]

    async def get_alarm_control_panel_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_alarm_control_panel(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state rather than fail the read; mirrors every prior M12
        # device-category service's own `get_X_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _alarm_control_panel_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands (no `code`/`pin` parameter anywhere -- Logic Contract §8)
    # ------------------------------------------------------------------
    async def arm_home(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, AlarmControlPanelCommand.ARM_HOME)

    async def arm_away(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, AlarmControlPanelCommand.ARM_AWAY)

    async def disarm(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, AlarmControlPanelCommand.DISARM)

    async def _send(self, device_id: str, command: AlarmControlPanelCommand) -> dict[str, Any]:
        device = await self._require_alarm_control_panel(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                "Alarm control panel control has no command translation for connector "
                f"type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}
