"""Smart Home Memory service -- Milestone 12 Smart Home Memory (Manual/
On-Demand Device Snapshot Slice + Device-Category Expansion Slice).

**Naming boundary, binding throughout this module.** A snapshot exists
only because this service's own method was called -- by a REST caller
or an agent tool, always in response to an explicit request. This is
not, and must never become, Device History, Continuous Device
Monitoring, Automatic State Tracking, or Event-Driven Memory. Nothing
here subscribes to an event, runs on a schedule, or triggers on a
device command; see the Logic Contract's own naming boundary
(``docs/M12_SMART_HOME_MEMORY_SNAPSHOT_LOGIC_CONTRACT.md``, this
module's original authoritative source, and
``docs/M12_SMART_HOME_MEMORY_EXPANSION_LOGIC_CONTRACT.md`` for the
Task Group S expansion below).

**Architecture**::

    SmartHomeMemoryService
        -> SmartHomeService (require_device / require_home / list_devices)
        -> {SmartLightingService, SmartSwitchService, ThermostatService}
           (get_light_state / get_switch_state / get_thermostat_state)
        -> {ApplianceService, VacuumHumidifierService,
            MediaPlayerService, WaterHeaterService}
           (get_fan_state / get_cover_state / get_vacuum_state /
            get_humidifier_state / get_media_player_state /
            get_water_heater_state)
        -> {SirenService, AlarmControlPanelService}
           (get_siren_state / get_alarm_control_panel_state)
        -> MemoryService (remember / browse / forget)

Never reaches a connector directly, never re-derives normalization --
every state dict this module persists is the owning service's own,
verbatim (Logic Contract §16/§17B).

**Device-category scope, Task Group S (Expansion Logic Contract §6-8)
+ Task Group V (Security Device Expansion Logic Contract).**
Eleven categories total. ``light``/``switch``/``thermostat`` each have
a unique ``device_type``, resolved by a direct dict lookup (Tier 1,
unchanged since Task Group O). ``fan``/``cover``/``vacuum``/
``humidifier``/``media_player``/``water_heater`` all share
``device_type="appliance"`` and are resolved by trying each owning
service's own already-public ``get_<category>_state`` method in turn
(Tier 2, `_read_state` below) -- never a private ``_domain_for``
duplicated, never a new shared domain-resolution abstraction.
``siren``/``alarm_control_panel`` both share ``device_type="other"``
and are resolved the identical way (Tier 3, Security Device Expansion
Logic Contract §7) -- trying `SirenService.get_siren_state`/
`AlarmControlPanelService.get_alarm_control_panel_state` in turn,
catching each one's own `ServiceError` as "not this category." Sensors
and Smart Locks remain **permanently excluded**, on privacy/security
grounds, not architectural ones -- re-verified, not re-opened, by the
Expansion Logic Contract's own §6/§9/§10 and reaffirmed again by Task
Group V: a persisted, browsable snapshot history of occupancy-revealing
sensor data or security-posture-revealing lock state is a materially
larger risk than either category's own already-established live-read
gating. Cameras remain out of scope -- no `CameraService` exists.

**Permission departs from the majority M12 precedent on purpose.**
Every prior appliance-category module's "reads ungated" decision was
made for a live, ephemeral read. A stored snapshot is persistent and
cumulatively browsable -- a series of snapshots can approximate a
presence signal even for "safe-tier" devices. Every operation this
module exposes -- :meth:`snapshot_device`, :meth:`list_snapshots`,
:meth:`delete_snapshot`, :meth:`snapshot_home` -- therefore requires
the same grant (Logic Contract §10, Expansion Logic Contract §14).

**Deletion is scoped, not generic (Expansion Logic Contract §12).**
:meth:`delete_snapshot` never calls ``MemoryService.forget()`` on an
unverified id -- it first confirms the target is actually a
``"device_snapshot"``-type memory via the same ``browse()`` method
:meth:`list_snapshots` already uses, so a caller holding only this
module's own grant can never delete a conversation memory, a workspace
memory, or any record this module didn't itself create.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.alarm_control_panel_service import AlarmControlPanelService
    from jarvis.services.appliance_service import ApplianceService
    from jarvis.services.media_player_service import MediaPlayerService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.siren_service import SirenService
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.smart_lighting_service import SmartLightingService
    from jarvis.services.smart_switch_service import SmartSwitchService
    from jarvis.services.thermostat_service import ThermostatService
    from jarvis.services.vacuum_humidifier_service import VacuumHumidifierService
    from jarvis.services.water_heater_service import WaterHeaterService

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

#: The shared `device_type` six appliance categories all register
#: under -- a local copy of the same literal every appliance-domain
#: service's own private constant already holds (Expansion Logic
#: Contract §7: this module never imports another service's private
#: constant, only the well-known shared vocabulary string itself).
_APPLIANCE_DEVICE_TYPE = "appliance"

#: The shared `device_type` Siren and alarm_control_panel both register
#: under -- a local copy of the same literal each of those services'
#: own private constant already holds (Security Device Expansion Logic
#: Contract §7, same "no private constant imported" principle
#: `_APPLIANCE_DEVICE_TYPE` above already establishes).
_OTHER_DEVICE_TYPE = "other"

#: Upper bound on how many snapshot-type records `delete_snapshot`
#: scans to confirm a target id is a real snapshot before calling
#: `MemoryService.forget()` -- the same over-fetch trade-off
#: `list_snapshots`' own device_id filter already accepts (no indexed
#: by-id-within-type query exists in `MemoryRepository` today; Expansion
#: Logic Contract §12).
_DELETE_SCAN_LIMIT = 1000


class SmartHomeMemoryPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, mirroring
    `security_service.SecurityPermissionError`'s own precedent, so
    `routes/smart_home_memory.py` can map it to 400 without confusing
    it with an unknown-device 404."""


class UnsupportedSnapshotCategoryError(ServiceError):
    """Raised when a device exists but its `device_type` (and, for the
    shared `"appliance"` bucket, its domain) falls outside the
    supported nine-category set (Logic Contract §5, Expansion Logic
    Contract §6-8). The device is real -- this is a distinct case from
    an unknown device, so `routes/smart_home_memory.py` maps it to
    400, not 404 (Logic Contract §18)."""


class SnapshotNotFoundError(ServiceError):
    """Raised by `delete_snapshot` when *memory_id* does not resolve
    to an existing `"device_snapshot"`-type memory record -- covers an
    unknown id, an id belonging to an unrelated memory type, and an
    already-deleted snapshot alike, deliberately indistinguishable
    from the caller's perspective (Expansion Logic Contract §12/§25).
    Mapped to 404, mirroring this module's own unknown-device
    convention."""


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


def _home_snapshot_result(
    device: Device,
    *,
    outcome: str,
    memory_id: str | None = None,
    detail: str | None = None,
) -> dict[str, Any]:
    """One `snapshot_home` result-array entry -- every device in the
    home appears exactly once, regardless of outcome (Expansion Logic
    Contract §13)."""
    return {
        "device_id": device.id,
        "device_name": device.name,
        "device_type": device.device_type,
        "outcome": outcome,
        "memory_id": memory_id,
        "detail": detail,
    }


class SmartHomeMemoryService:
    def __init__(
        self,
        *,
        smart_home: SmartHomeService,
        smart_lighting: SmartLightingService,
        smart_switch: SmartSwitchService,
        thermostats: ThermostatService,
        appliances: ApplianceService,
        vacuum_humidifier: VacuumHumidifierService,
        media_players: MediaPlayerService,
        water_heaters: WaterHeaterService,
        siren: SirenService,
        alarm_control_panels: AlarmControlPanelService,
        memory: MemoryService,
        permissions: PermissionModel,
    ) -> None:
        self._smart_home = smart_home
        self._memory = memory
        self._permissions = permissions
        self._permissions.declare(SMART_HOME_MEMORY_PRINCIPAL, [SMART_HOME_SCOPE])
        # device_type -> the owning service's own read method (Tier 1).
        # Closed to the three unique-device_type categories -- a device
        # type not present here either resolves via Tier 2 (appliance
        # domains, below) or is a real, reportable gap (`_read_state`),
        # never a silent skip.
        self._readers: dict[str, _DeviceStateReader] = {
            "light": smart_lighting.get_light_state,
            "switch": smart_switch.get_switch_state,
            "thermostat": thermostats.get_thermostat_state,
        }
        # Ordered (name, reader) cascade for the shared "appliance"
        # device_type (Tier 2) -- Expansion Logic Contract §7. Each
        # reader is that category's own already-public `get_<category>
        # _state`; a `ServiceError` from one candidate means "not this
        # category," never a private `_domain_for` re-implemented here.
        self._appliance_readers: list[tuple[str, _DeviceStateReader]] = [
            ("fan", appliances.get_fan_state),
            ("cover", appliances.get_cover_state),
            ("vacuum", vacuum_humidifier.get_vacuum_state),
            ("humidifier", vacuum_humidifier.get_humidifier_state),
            ("media_player", media_players.get_media_player_state),
            ("water_heater", water_heaters.get_water_heater_state),
        ]
        # Ordered (name, reader) cascade for the shared "other"
        # device_type (Tier 3) -- Security Device Expansion Logic
        # Contract §7. Same shape as Tier 2 above: each reader is that
        # category's own already-public `get_<category>_state`; a
        # `ServiceError` from one candidate means "not this category,"
        # never a private `_domain_for` re-implemented here. Ordered to
        # match ship order (Siren, Task Group R, before
        # alarm_control_panel, Task Group U) -- the two domains are
        # mutually exclusive, so order has no effect on outcome.
        self._security_readers: list[tuple[str, _DeviceStateReader]] = [
            ("siren", siren.get_siren_state),
            ("alarm_control_panel", alarm_control_panels.get_alarm_control_panel_state),
        ]

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

    async def _read_state(self, device: Device) -> dict[str, Any]:
        """Resolves *device* to its owning service's normalized state,
        Tier 1 (unique `device_type`) then Tier 2 (shared `"appliance"`
        cascade) then Tier 3 (shared `"other"` cascade, Security Device
        Expansion Logic Contract §7). Raises
        `UnsupportedSnapshotCategoryError` if no tier resolves it --
        callers have already confirmed the device itself exists
        (`SmartHomeService.require_device`/`list_devices`), so this is
        purely a category-support decision, never conflated with
        "unknown device" (Expansion Logic Contract §7)."""
        reader = self._readers.get(device.device_type)
        if reader is not None:
            return await reader(device.id)
        if device.device_type == _APPLIANCE_DEVICE_TYPE:
            for _name, appliance_reader in self._appliance_readers:
                try:
                    return await appliance_reader(device.id)
                except ServiceError:
                    continue
        if device.device_type == _OTHER_DEVICE_TYPE:
            for _name, security_reader in self._security_readers:
                try:
                    return await security_reader(device.id)
                except ServiceError:
                    continue
        raise UnsupportedSnapshotCategoryError(
            f"Device {device.id!r} is a {device.device_type!r}; snapshotting is only "
            "supported for light/switch/thermostat/fan/cover/vacuum/humidifier/"
            "media_player/water_heater/siren/alarm_control_panel devices in this release."
        )

    async def _capture_snapshot(self, device: Device) -> dict[str, Any]:
        """Reads and persists one snapshot for *device*. Shared by
        `snapshot_device` and `snapshot_home` so both stay byte-for-byte
        consistent in what they capture and how -- an unavailable
        device still produces an honest snapshot (the owning service's
        own read already reports `available: false`/`None` live fields
        rather than raising), and this method persists whatever it
        returns verbatim, never fabricating a substitute (Logic
        Contract §18/§20)."""
        state = await self._read_state(device)
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
    # Snapshot
    # ------------------------------------------------------------------
    async def snapshot_device(self, device_id: str) -> dict[str, Any]:
        """Captures *device_id*'s current normalized state into memory,
        once, because this call was made."""
        self._require_permission()
        device = await self._smart_home.require_device(device_id)
        return await self._capture_snapshot(device)

    async def snapshot_home(self, home_id: str) -> dict[str, Any]:
        """Snapshots every device in *home_id* whose category this
        module supports; skips the rest. Sequential, partial-success,
        never aborts on one device's failure (Expansion Logic Contract
        §13). Read-only against devices -- never sends a device a
        command -- so, unlike Panic/Vacation Mode, no confirmation is
        required (Expansion Logic Contract §15)."""
        self._require_permission()
        await self._smart_home.require_home(home_id)
        devices = await self._smart_home.list_devices(home_id=home_id)

        results: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        skipped = 0
        for device in devices:
            try:
                summary = await self._capture_snapshot(device)
            except UnsupportedSnapshotCategoryError:
                skipped += 1
                results.append(
                    _home_snapshot_result(
                        device,
                        outcome="skipped",
                        detail="Device category is not supported for snapshotting.",
                    )
                )
                continue
            except Exception as err:  # a per-device failure must never abort the batch (§13)
                failed += 1
                results.append(_home_snapshot_result(device, outcome="failed", detail=str(err)))
                continue
            succeeded += 1
            results.append(
                _home_snapshot_result(device, outcome="succeeded", memory_id=summary["memory_id"])
            )

        return {
            "home_id": home_id,
            "requested_count": len(devices),
            "attempted_count": succeeded + failed,
            "succeeded_count": succeeded,
            "failed_count": failed,
            "skipped_count": skipped,
            "results": results,
            "generated_at": datetime.now(UTC).isoformat(),
        }

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

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------
    async def delete_snapshot(self, memory_id: str) -> dict[str, Any]:
        """Deletes one snapshot by memory id -- never a generic memory
        delete. Confirms *memory_id* actually names a
        `"device_snapshot"`-type record (via the same `browse()` this
        module's own retrieval already uses) before calling the
        existing, unmodified `MemoryService.forget()`; an unknown id, an
        id belonging to an unrelated memory type, and an already-deleted
        snapshot are all indistinguishable `SnapshotNotFoundError`s
        (Expansion Logic Contract §12/§25)."""
        self._require_permission()
        records = await self._memory.browse(
            memory_type=SNAPSHOT_MEMORY_TYPE, limit=_DELETE_SCAN_LIMIT
        )
        if not any(r.id == memory_id for r in records):
            raise SnapshotNotFoundError(f"No device snapshot with id {memory_id!r} exists.")
        await self._memory.forget(memory_id)
        return {"memory_id": memory_id, "deleted": True}
