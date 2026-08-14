"""Smart Home Memory service -- Milestone 12 Smart Home Memory (Manual/
On-Demand Device Snapshot Slice).

**Naming boundary, binding throughout this module.** A snapshot exists
only because this service's own method was called -- by a REST caller
or an agent tool, always in response to an explicit request. This is
not, and must never become, Device History, Continuous Device
Monitoring, Automatic State Tracking, or Event-Driven Memory. Nothing
here subscribes to an event, runs on a schedule, or triggers on a
device command; see the Logic Contract's own naming boundary
(``docs/M12_SMART_HOME_MEMORY_SNAPSHOT_LOGIC_CONTRACT.md``, this
module's authoritative source).

**Architecture**::

    SmartHomeMemoryService
        -> SmartHomeService (require_device: device_type/home_id/room_id/name)
        -> {SmartLightingService, SmartSwitchService, ThermostatService}
           (get_light_state / get_switch_state / get_thermostat_state)
        -> MemoryService (remember / browse)

Never reaches a connector directly, never re-derives normalization --
every state dict this module persists is the owning service's own,
verbatim (Logic Contract §16/§17B).

**Device-category scope is deliberately narrow (Logic Contract §5).**
Only ``light``/``switch``/``thermostat`` are supported: each has a
unique ``device_type``, so a device's type alone resolves which
service owns it, with no private domain-resolution step to duplicate
(unlike ``vacuum``/``humidifier``/``media_player``/``water_heater``,
which all share ``device_type="appliance"`` and are distinguished only
by each service's own *private* domain helper). Sensors and Smart
Locks are excluded for a separate, privacy/security reason, not an
architectural one: a persisted, browsable snapshot history of
occupancy-revealing sensor data or security-posture-revealing lock
state is a materially larger risk than either category's own
already-established live-read gating.

**Permission departs from the majority M12 precedent on purpose.**
Every prior appliance-category module's "reads ungated" decision was
made for a live, ephemeral read. A stored snapshot is persistent and
cumulatively browsable -- a series of snapshots can approximate a
presence signal even for "safe-tier" devices. Both
:meth:`snapshot_device` and :meth:`list_snapshots` therefore require
the same grant (Logic Contract §10).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.smart_lighting_service import SmartLightingService
    from jarvis.services.smart_switch_service import SmartSwitchService
    from jarvis.services.thermostat_service import ThermostatService

    _DeviceStateReader = Callable[[str], Awaitable[dict[str, Any]]]

#: The `PermissionModel` identity this module declares and checks
#: against -- one fixed principal, mirroring every other M12 module's
#: naming.
SMART_HOME_MEMORY_PRINCIPAL = "core:smart_home_memory"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

#: `memory_type` and `source` for every snapshot memory row -- both set
#: to the same literal deliberately (Logic Contract §6): `memory_type`
#: is the retrieval discriminator, `source` records the mechanism that
#: produced the memory, and "device_snapshot" is the accurate answer to
#: both regardless of whether a human or an agent triggered the call.
SNAPSHOT_MEMORY_TYPE = "device_snapshot"

#: Every owning service's own normalized payload carries these identity
#: fields -- excluded from the embedded content text since they are
#: already duplicated, verbatim, in snapshot metadata (Logic Contract
#: §17A).
_IDENTITY_KEYS = frozenset(
    {"id", "home_id", "room_id", "name", "status", "manufacturer", "model", "external_id"}
)


class SmartHomeMemoryPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, mirroring
    `security_service.SecurityPermissionError`'s own precedent, so
    `routes/smart_home_memory.py` can map it to 400 without confusing
    it with an unknown-device 404."""


class UnsupportedSnapshotCategoryError(ServiceError):
    """Raised when a device exists but its `device_type` falls outside
    the supported light/switch/thermostat set (Logic Contract §5). The
    device is real -- this is a distinct case from an unknown device,
    so `routes/smart_home_memory.py` maps it to 400, not 404 (Logic
    Contract §18)."""


def _snapshot_content(
    *,
    device_name: str,
    device_type: str,
    home_id: str,
    room_id: str | None,
    state: dict[str, Any],
    snapshot_at: str,
) -> str:
    """Deterministic template text -- no LLM generation happens here
    (Logic Contract §17A). `MemoryService.remember` embeds this string
    via its own best-effort step; this module never talks to an LLM
    directly."""
    where = f"home {home_id}" + (f", room {room_id}" if room_id else "")
    parts = [f"{key}={value}" for key, value in state.items() if key not in _IDENTITY_KEYS]
    summary = ", ".join(parts) if parts else "no additional state reported"
    return (
        f"Snapshot of {device_name} ({device_type}) in {where}: {summary}. "
        f"Captured at {snapshot_at}."
    )


def _snapshot_summary(memory_id: str, device: Device, snapshot_at: str) -> dict[str, Any]:
    return {
        "memory_id": memory_id,
        "device_id": device.id,
        "device_type": device.device_type,
        "snapshot_at": snapshot_at,
    }


class SmartHomeMemoryService:
    def __init__(
        self,
        *,
        smart_home: SmartHomeService,
        smart_lighting: SmartLightingService,
        smart_switch: SmartSwitchService,
        thermostats: ThermostatService,
        memory: MemoryService,
        permissions: PermissionModel,
    ) -> None:
        self._smart_home = smart_home
        self._memory = memory
        self._permissions = permissions
        self._permissions.declare(SMART_HOME_MEMORY_PRINCIPAL, [SMART_HOME_SCOPE])
        # device_type -> the owning service's own read method. Closed to
        # the Logic Contract §5 MVP set -- a device type not present
        # here is a real, reportable gap (`_require_supported_device`),
        # never a silent skip.
        self._readers: dict[str, _DeviceStateReader] = {
            "light": smart_lighting.get_light_state,
            "switch": smart_switch.get_switch_state,
            "thermostat": thermostats.get_thermostat_state,
        }

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SMART_HOME_MEMORY_PRINCIPAL, SMART_HOME_SCOPE):
            raise SmartHomeMemoryPermissionError(
                "Device snapshots require the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SMART_HOME_MEMORY_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SMART_HOME_MEMORY_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    async def _require_supported_device(self, device_id: str) -> Device:
        device = await self._smart_home.require_device(device_id)
        if device.device_type not in self._readers:
            raise UnsupportedSnapshotCategoryError(
                f"Device {device_id!r} is a {device.device_type!r}; snapshotting is "
                "only supported for light/switch/thermostat devices in this release."
            )
        return device

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------
    async def snapshot_device(self, device_id: str) -> dict[str, Any]:
        """Captures *device_id*'s current normalized state into memory,
        once, because this call was made. An unavailable device still
        produces an honest snapshot -- the owning service's own read
        already reports `available: false`/`None` live fields rather
        than raising, and this method persists whatever it returns
        verbatim, never fabricating a substitute (Logic Contract §18/
        §20)."""
        self._require_permission()
        device = await self._require_supported_device(device_id)
        reader = self._readers[device.device_type]
        state = await reader(device_id)

        snapshot_at = datetime.now(UTC).isoformat()
        content = _snapshot_content(
            device_name=device.name,
            device_type=device.device_type,
            home_id=device.home_id,
            room_id=device.room_id,
            state=state,
            snapshot_at=snapshot_at,
        )
        metadata = {
            "device_id": device.id,
            "device_type": device.device_type,
            "home_id": device.home_id,
            "room_id": device.room_id,
            "device_name": device.name,
            "snapshot_at": snapshot_at,
            "state": state,
        }
        memory_id = await self._memory.remember(
            content,
            source=SNAPSHOT_MEMORY_TYPE,
            memory_type=SNAPSHOT_MEMORY_TYPE,
            metadata=metadata,
        )
        return _snapshot_summary(memory_id, device, snapshot_at)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------
    async def list_snapshots(
        self, *, device_id: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Most-recent-first, reusing `MemoryService.browse` verbatim
        (Logic Contract §7) -- no new query subsystem. When *device_id*
        is given, over-fetches from `browse()` and filters client-side
        by `metadata["device_id"]`; there is no indexed per-device
        query in `MemoryRepository` today, a documented limitation, not
        a hidden one."""
        self._require_permission()
        fetch_limit = limit if device_id is None else min(max(limit * 5, limit), 500)
        records = await self._memory.browse(memory_type=SNAPSHOT_MEMORY_TYPE, limit=fetch_limit)
        if device_id is not None:
            records = [r for r in records if r.metadata.get("device_id") == device_id]
        records = records[:limit]
        return [
            {
                "memory_id": r.id,
                "device_id": r.metadata.get("device_id"),
                "device_type": r.metadata.get("device_type"),
                "home_id": r.metadata.get("home_id"),
                "room_id": r.metadata.get("room_id"),
                "device_name": r.metadata.get("device_name"),
                "snapshot_at": r.metadata.get("snapshot_at"),
                "state": r.metadata.get("state"),
                "content": r.content,
            }
            for r in records
        ]
