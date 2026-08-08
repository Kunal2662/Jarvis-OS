"""Smart Lock service -- Milestone 12 Smart Locks.

The thin orchestration layer `docs/M12_SMART_LOCKS_LOGIC_CONTRACT.md`
requires: two normalized commands (`lock`, `unlock`) translated into
each connector's wire format, through
:meth:`ConnectivityService.send_command` -- the same chokepoint every
other M12 caller already uses, never a second execution path. Mirrors
`services/smart_lighting_service.py`'s exact shape, reduced to a
single-attribute device: no attribute-merge case exists here (a lock
has exactly one property), so unlike lighting's translators there is
no "combine several changed attributes into one wire call" concern --
every call is one wire command.

**Permission enforcement reuses the existing Permission Engine.** Same
mechanism, same `smart_home` scope, a new fixed principal
(`core:smart_locks`, mirroring `core:smart_lighting`'s naming) --
declared once at construction, `PENDING` by default, granted through
the same existing generic route
(`POST /api/v1/plugins/{principal}/permissions/{scope}/grant`).

**No access history, no fan-out, no scenes.** Per the Logic Contract:
none of these are genuinely supported by existing infrastructure
without new tables or event plumbing this module was not asked to add
-- see the Logic Contract §16 for the full reasoning.
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
#: `smart_lighting_service.SMART_LIGHTING_PRINCIPAL`'s exact naming and
#: reasoning.
SMART_LOCK_PRINCIPAL = "core:smart_locks"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- the same one Smart Lighting enforces; locks
#: and lights are not separately scoped.
SMART_HOME_SCOPE = "smart_home"

_LOCK_DEVICE_TYPE = "lock"

#: Raw connector status strings that mean "locked"/"unlocked" -- the
#: same best-effort, non-closed-vocabulary heuristic
#: `smart_lighting_service._infer_on` already established for on/off.
#: Anything else (`"jammed"`, `"locking"`, `"unlocking"`, or unread)
#: reports `locked=None` -- neither connector normalizes those into
#: anything today, so this module does not invent handling for states
#: the connector layer itself does not represent.
_LOCKED_STATUS_VALUES = frozenset({"locked", "true", "1"})
_UNLOCKED_STATUS_VALUES = frozenset({"unlocked", "false", "0"})


class LockCommand(enum.StrEnum):
    """The normalized command vocabulary this module supports."""

    LOCK = "lock"
    UNLOCK = "unlock"


def _translate_home_assistant(command: LockCommand) -> tuple[str, dict[str, Any]]:
    """HA's own lock-domain service names, no payload fields -- verified
    directly against the shipped `HomeAssistantConnector.send_command`
    this session (domain/service split from `entity_id`, body =
    `{"entity_id": ..., **payload}`)."""
    return command.value, {}


def _translate_mqtt(command: LockCommand) -> tuple[str, dict[str, Any]]:
    """A new JARVIS-native vocabulary this module defines (no lock
    consumer of `mqtt_envelope.py`'s free-form command/args existed
    before it) -- deliberately mirrors HA's own service names for
    cross-connector predictability, verified against the shipped
    `MqttConnector.send_command`/`build_command_envelope` this session."""
    return command.value, {}


#: Connector type -> translator. Closed to `CONNECTOR_TYPES`
#: (`core/interfaces/connectivity.py`) by construction -- a connector
#: type with no entry here is a real, reportable gap, never a silent
#: no-op.
_TRANSLATORS = {
    "home_assistant": _translate_home_assistant,
    "mqtt": _translate_mqtt,
}


def _infer_locked(status: str) -> bool | None:
    normalized = status.strip().lower()
    if normalized in _LOCKED_STATUS_VALUES:
        return True
    if normalized in _UNLOCKED_STATUS_VALUES:
        return False
    return None


def _lock_payload(device: Device, raw: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": device.id,
        "home_id": device.home_id,
        "room_id": device.room_id,
        "name": device.name,
        "status": device.status,
        "manufacturer": device.manufacturer,
        "model": device.model,
        "external_id": device.external_id,
        "locked": None,
        "available": raw is not None,
    }
    if raw is not None:
        payload["locked"] = _infer_locked(raw.status)
    return payload


class SmartLockService:
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
        self._permissions.declare(SMART_LOCK_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE):
            raise ServiceError(
                "Smart Lock control requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SMART_LOCK_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SMART_LOCK_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def _require_lock(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _LOCK_DEVICE_TYPE:
            raise ServiceError(f"Device {device_id!r} is a {device.device_type!r}, not a lock.")
        return device

    async def list_locks(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Last-known DB records only -- no live connector read per
        lock, the same list/detail asymmetry `SmartLightingService.
        list_lights`/`get_light_state` already draw."""
        devices = await self._smart_home.list_devices(
            home_id=home_id, room_id=room_id, device_type=_LOCK_DEVICE_TYPE
        )
        return [_lock_payload(d) for d in devices]

    async def get_lock_state(self, device_id: str) -> dict[str, Any]:
        device = await self._require_lock(device_id)
        raw = None
        # Connector unreachable/not connected -- report last-known DB
        # state (locked=None, available=False) rather than fail the
        # read; mirrors `SmartLightingService.get_light_state`.
        with contextlib.suppress(ConnectivityError):
            raw = await self._connectivity.read_raw_state(device_id)
        return _lock_payload(device, raw)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    async def lock(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, LockCommand.LOCK)

    async def unlock(self, device_id: str) -> dict[str, Any]:
        self._require_permission()
        return await self._send(device_id, LockCommand.UNLOCK)

    async def _send(self, device_id: str, command: LockCommand) -> dict[str, Any]:
        device = await self._require_lock(device_id)
        connector_type = connector_type_for(device)
        if connector_type is None:
            raise ServiceError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        translator = _TRANSLATORS.get(connector_type)
        if translator is None:
            raise ServiceError(
                f"Smart Locks has no command translation for connector type {connector_type!r}."
            )
        wire_command, payload = translator(command)
        result = await self._connectivity.send_command(device_id, wire_command, payload)
        return {"device_id": device_id, "success": result.success, "detail": result.detail}
