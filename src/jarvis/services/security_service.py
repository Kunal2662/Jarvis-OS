"""Security & Safety service -- Milestone 12 Security & Safety
(Read-Only Alert/Status Slice + Manual/On-Demand Action Slice).

`docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md` §13 defines the read-only
half of this module's contract: a **pull-based aggregation** over two
already-shipped services -- `SensorService` and `SmartLockService` --
never a connector, never `ConnectivityService`/`SmartHomeService`
directly. `docs/M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md` defines
the second half, added by Task Group M: two synchronous, on-demand,
home-scoped orchestration actions -- **Panic Mode** (lock every lock,
turn on every light) and **Vacation Mode** (lock every lock, turn off
every light, best-effort eco-adjust every thermostat that reports the
capability). This module still owns no device category and adds no
persistence -- it composes `SmartLockService`/`SmartLightingService`/
`ThermostatService`'s own existing public methods, the write-side
mirror of how it already composes `SensorService`/`SmartLockService`
read-only. Extending this class rather than creating a sibling service
was a deliberate Logic Contract decision (§2): Panic/Vacation Mode are
not a new device category the way Appliance Control's siblings are --
they are a second capability over the same "home security posture"
concept this module already owns.

**Every operation requires the `smart_home` permission for the
existing `core:security` principal** -- independently of
`SensorService`'s own `core:sensors` grant, `SmartLockService`'s own
`core:smart_locks` grant, `SmartLightingService`'s own
`core:smart_lighting` grant, and `ThermostatService`'s own
`core:thermostats` grant (Logic Contract §3/§14 for reads; Action
Slice Logic Contract §7/§11 for actions). This module never catches or
suppresses a nested permission error from a top-level check -- a
missing `core:sensors` grant still fails `get_security_status` openly.
A missing nested grant *inside* a bulk action (`core:smart_locks`/
`core:smart_lighting`/`core:thermostats`) is different: it surfaces as
an ordinary **per-device failure** within that bulk action's own
continue-past-failure loop (Action Slice Logic Contract §7), never a
top-level exception that would abort every other device.

**Alert semantics are closed and non-inferred** (Logic Contract §4):
only `smoke`/`gas`/`moisture` (water leak) -- HA's own literal
"hazard detected" `device_class` values -- can become an active alert.
`door`/`window`/`garage_door`/`motion`/`presence`/`occupancy`/
`vibration` and lock state are always reported as factual status only;
none of them is ever elevated to an alert or allowed to move
`overall_status`. This is a structural invariant, not a per-case
judgment call.

**Panic Mode / Vacation Mode are synchronous and single-shot.** No
`EventBus` publish/subscribe, no scheduling, no background worker, no
retry loop -- each call runs once and returns its complete result.
Neither action ever claims atomicity: a partial failure across many
devices is reported honestly (`status: "PARTIAL_SUCCESS"`), never
hidden behind a single boolean.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError

if TYPE_CHECKING:
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.services.sensor_service import SensorService
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.smart_lighting_service import SmartLightingService
    from jarvis.services.smart_lock_service import SmartLockService
    from jarvis.services.thermostat_service import ThermostatService

#: The `PermissionModel` identity this module declares and checks
#: against -- mirrors `SENSOR_PRINCIPAL`/`SMART_LOCK_PRINCIPAL`'s exact
#: naming and reasoning. Independently grantable from `core:sensors` --
#: granting one does NOT grant the other (Logic Contract §3).
SECURITY_PRINCIPAL = "core:security"

#: The pre-existing, shared scope (`core/plugins/sdk.py`'s
#: `PERMISSION_SCOPES`) -- no new scope is created.
SMART_HOME_SCOPE = "smart_home"

#: `device_class` values whose `value=True` reading is HA's own literal
#: "hazard detected" meaning -- the only classes that can produce an
#: active alert or move `overall_status` off NORMAL/UNKNOWN. Closed,
#: per Logic Contract §4.
_HAZARD_DEVICE_CLASSES = frozenset({"smoke", "gas", "moisture"})

#: `device_class` values reported as factual status only -- never an
#: alert, never affects `overall_status`, per Logic Contract §4. Any
#: other `device_class` (temperature, humidity, illuminance, energy,
#: ...) is outside this module's aggregate entirely.
_STATUS_DEVICE_CLASSES = frozenset(
    {"door", "window", "garage_door", "motion", "presence", "occupancy", "vibration"}
)

#: `Device.status` values meaning "this device is unreachable" -- the
#: same connectivity-lifecycle vocabulary Task Group A/B established,
#: used here as the one signal reliably present across locks *and*
#: lights despite `SmartLightingService`'s own read model exposing no
#: `available` field at all (Action Slice Logic Contract §3/§6).
_UNAVAILABLE_STATUS_VALUES = frozenset({"offline", "unreachable"})

#: The one HVAC mode this module will ever request for Vacation Mode's
#: best-effort thermostat adjustment -- checked against each device's
#: own reported `hvac_modes`, never assumed. Action Slice Logic
#: Contract §5: no `preset_mode` use (not exposed by `ThermostatService`
#: today), no temperature fallback, no invented capability.
_ECO_HVAC_MODE = "eco"


def _device_unavailable(status: str) -> bool:
    return status.strip().lower() in _UNAVAILABLE_STATUS_VALUES


class SecurityPermissionError(ServiceError):
    """Raised by `_require_permission()` specifically -- a distinct
    subclass, not a bare `ServiceError`, mirroring
    `sensor_service.SensorPermissionError`'s own precedent. Kept local
    to this module since nothing outside it needs to catch it
    specifically -- `routes/security.py` catches the shared
    `ServiceError` base instead (this module has no 404 case to
    distinguish from, unlike Sensors -- Logic Contract §12)."""


def _hazard_signal(state: dict[str, Any]) -> str:
    """`"ACTIVE"` / `"CLEAR"` / `"UNKNOWN"` -- derived only from fields
    `SensorService.get_sensor_state` already returns. `"UNKNOWN"` is
    never coalesced into `"CLEAR"` -- unavailable/unparseable data is
    never interpreted as safe (Logic Contract §5)."""
    if not state["available"]:
        return "UNKNOWN"
    value = state["value"]
    if value is None:
        return "UNKNOWN"
    return "ACTIVE" if value else "CLEAR"


def _overall_status(hazard_sensors: list[dict[str, Any]]) -> str:
    """Logic Contract §6's precedence, computed only from the hazard
    bucket -- status sensors and lock state never participate."""
    if not hazard_sensors:
        return "UNKNOWN"
    signals = {entry["signal"] for entry in hazard_sensors}
    if "ACTIVE" in signals:
        return "CRITICAL"
    if "UNKNOWN" in signals:
        return "WARNING"
    return "NORMAL"


class SecurityService:
    def __init__(
        self,
        *,
        sensors: SensorService,
        smart_lock: SmartLockService,
        smart_lighting: SmartLightingService,
        thermostats: ThermostatService,
        smart_home: SmartHomeService,
        permissions: PermissionModel,
    ) -> None:
        self._sensors = sensors
        self._smart_lock = smart_lock
        self._smart_lighting = smart_lighting
        self._thermostats = thermostats
        self._smart_home = smart_home
        self._permissions = permissions
        self._permissions.declare(SECURITY_PRINCIPAL, [SMART_HOME_SCOPE])

    # ------------------------------------------------------------------
    # Permission
    # ------------------------------------------------------------------
    def _require_permission(self) -> None:
        if not self._permissions.is_granted(SECURITY_PRINCIPAL, SMART_HOME_SCOPE):
            raise SecurityPermissionError(
                "Security status access requires the "
                f"{SMART_HOME_SCOPE!r} permission to be granted for "
                f"{SECURITY_PRINCIPAL!r}. Grant it via POST "
                f"/api/v1/plugins/{SECURITY_PRINCIPAL}/permissions/"
                f"{SMART_HOME_SCOPE}/grant."
            )

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------
    async def get_security_status(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> dict[str, Any]:
        self._require_permission()

        # Not caught here -- a SensorPermissionError from `core:sensors`
        # not being granted propagates as-is (it is itself a
        # ServiceError). Logic Contract §3: this module has no
        # legitimate way to report a truthful status while missing the
        # sensor data it is built on.
        sensor_rows = await self._sensors.list_sensors(home_id=home_id, room_id=room_id)
        lock_rows = await self._smart_lock.list_locks(home_id=home_id, room_id=room_id)

        hazard_sensors: list[dict[str, Any]] = []
        status_sensors: list[dict[str, Any]] = []
        active_alerts: list[dict[str, Any]] = []
        unavailable_count = 0

        for row in sensor_rows:
            device_class = row.get("device_class")
            if device_class in _HAZARD_DEVICE_CLASSES:
                state = await self._sensors.get_sensor_state(row["id"])
                signal = _hazard_signal(state)
                if signal == "UNKNOWN":
                    unavailable_count += 1
                entry = {
                    "device_id": row["id"],
                    "name": row["name"],
                    "room_id": row["room_id"],
                    "device_class": device_class,
                    "signal": signal,
                    "available": state["available"],
                    "timestamp": state["timestamp"],
                }
                hazard_sensors.append(entry)
                if signal == "ACTIVE":
                    active_alerts.append(
                        {
                            "device_id": row["id"],
                            "name": row["name"],
                            "room_id": row["room_id"],
                            "device_class": device_class,
                            "timestamp": state["timestamp"],
                        }
                    )
            elif device_class in _STATUS_DEVICE_CLASSES:
                state = await self._sensors.get_sensor_state(row["id"])
                status_sensors.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "room_id": row["room_id"],
                        "device_class": device_class,
                        "state": state["state"],
                        "available": state["available"],
                        "timestamp": state["timestamp"],
                    }
                )

        locks: list[dict[str, Any]] = []
        for row in lock_rows:
            lock_state = await self._smart_lock.get_lock_state(row["id"])
            if not lock_state["available"]:
                unavailable_count += 1
            locks.append(
                {
                    "device_id": row["id"],
                    "name": row["name"],
                    "room_id": row["room_id"],
                    "locked": lock_state["locked"],
                    "available": lock_state["available"],
                }
            )

        return {
            "home_id": home_id,
            "room_id": room_id,
            "overall_status": _overall_status(hazard_sensors),
            "active_alerts": active_alerts,
            "hazard_sensors": hazard_sensors,
            "status_sensors": status_sensors,
            "locks": locks,
            "unavailable_count": unavailable_count,
            "generated_at": datetime.now(UTC).isoformat(),
        }

    async def list_active_alerts(
        self, *, home_id: str | None = None, room_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Thin slice of `get_security_status` -- Logic Contract §11's
        terser, alert-only projection for the agent tool layer. Not a
        second aggregation path; it delegates to the same call."""
        status = await self.get_security_status(home_id=home_id, room_id=room_id)
        alerts: list[dict[str, Any]] = status["active_alerts"]
        return alerts

    # ------------------------------------------------------------------
    # Manual/On-Demand Actions (gated -- Action Slice Logic Contract §11)
    # ------------------------------------------------------------------
    async def trigger_panic_mode(self, home_id: str) -> dict[str, Any]:
        """Lock every lock and turn on every light in *home_id*, once,
        synchronously. Never unlocks, never turns anything off, never
        touches thermostats/cameras/sirens, never schedules or
        publishes an event (Action Slice Logic Contract §4)."""
        self._require_permission()
        await self._smart_home.require_home(home_id)

        lock_results, lock_ok, lock_failed, lock_unavailable = await self._bulk_locks(home_id)
        light_results, light_ok, light_failed, light_unavailable = await self._bulk_lights(
            home_id, on=True
        )

        return self._build_action_result(
            home_id=home_id,
            mode="panic",
            locks=lock_results,
            lights=light_results,
            thermostats=[],
            succeeded=lock_ok + light_ok,
            failed=lock_failed + light_failed,
            unavailable=lock_unavailable + light_unavailable,
            skipped=0,
        )

    async def trigger_vacation_mode(self, home_id: str) -> dict[str, Any]:
        """Lock every lock, turn off every light, and best-effort
        eco-adjust every thermostat that reports an `"eco"` HVAC mode
        in *home_id*, once, synchronously. Never invents a capability
        a device did not report -- a thermostat with no eco-adjacent
        `hvac_mode` is skipped, not defaulted (Action Slice Logic
        Contract §5)."""
        self._require_permission()
        await self._smart_home.require_home(home_id)

        lock_results, lock_ok, lock_failed, lock_unavailable = await self._bulk_locks(home_id)
        light_results, light_ok, light_failed, light_unavailable = await self._bulk_lights(
            home_id, on=False
        )
        (
            thermostat_results,
            thermostat_ok,
            thermostat_failed,
            thermostat_unavailable,
            thermostat_skipped,
        ) = await self._bulk_thermostats_eco(home_id)

        return self._build_action_result(
            home_id=home_id,
            mode="vacation",
            locks=lock_results,
            lights=light_results,
            thermostats=thermostat_results,
            succeeded=lock_ok + light_ok + thermostat_ok,
            failed=lock_failed + light_failed + thermostat_failed,
            unavailable=lock_unavailable + light_unavailable + thermostat_unavailable,
            skipped=thermostat_skipped,
        )

    # ------------------------------------------------------------------
    # Action helpers -- per-category bulk orchestration, continues past
    # individual device failure (Action Slice Logic Contract §4/§7)
    # ------------------------------------------------------------------
    async def _bulk_locks(self, home_id: str) -> tuple[list[dict[str, Any]], int, int, int]:
        """Locks every lock in *home_id*. Returns (per-device results,
        succeeded, failed, unavailable). Never raises -- a nested
        `ServiceError` (including a `core:smart_locks` permission
        denial) is caught and recorded as a per-device failure, never
        propagated (Action Slice Logic Contract §7)."""
        rows = await self._smart_lock.list_locks(home_id=home_id)
        results: list[dict[str, Any]] = []
        succeeded = failed = unavailable = 0
        for row in rows:
            if _device_unavailable(row["status"]):
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": "device unavailable",
                    }
                )
                unavailable += 1
                continue
            try:
                outcome = await self._smart_lock.lock(row["id"])
            except ServiceError as err:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": str(err),
                    }
                )
                failed += 1
                continue
            results.append(
                {
                    "device_id": row["id"],
                    "name": row["name"],
                    "success": outcome["success"],
                    "detail": outcome["detail"],
                }
            )
            if outcome["success"]:
                succeeded += 1
            else:
                failed += 1
        return results, succeeded, failed, unavailable

    async def _bulk_lights(
        self, home_id: str, *, on: bool
    ) -> tuple[list[dict[str, Any]], int, int, int]:
        """Sets every light in *home_id* to *on*. Same shape/discipline
        as `_bulk_locks` -- `SmartLightingService`'s own `apply_room`/
        `apply_group` already establish "catch `ServiceError` per
        device, continue" via their private `_safe_set`; this method
        reimplements that pattern at home scope rather than calling
        into a room/group-scoped method (Action Slice Logic Contract
        §3)."""
        rows = await self._smart_lighting.list_lights(home_id=home_id)
        results: list[dict[str, Any]] = []
        succeeded = failed = unavailable = 0
        for row in rows:
            if _device_unavailable(row["status"]):
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": "device unavailable",
                    }
                )
                unavailable += 1
                continue
            try:
                outcome = await self._smart_lighting.set_light_state(row["id"], on=on)
            except ServiceError as err:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": str(err),
                    }
                )
                failed += 1
                continue
            results.append(
                {
                    "device_id": row["id"],
                    "name": row["name"],
                    "success": outcome["success"],
                    "detail": outcome["detail"],
                }
            )
            if outcome["success"]:
                succeeded += 1
            else:
                failed += 1
        return results, succeeded, failed, unavailable

    async def _bulk_thermostats_eco(
        self, home_id: str
    ) -> tuple[list[dict[str, Any]], int, int, int, int]:
        """Best-effort eco-adjusts every thermostat in *home_id* that
        reports `"eco"` in its own `hvac_modes` -- never a temperature
        fallback, never an invented preset (Action Slice Logic
        Contract §5). Returns (per-device results, succeeded, failed,
        unavailable, skipped). `list_thermostats` never populates live
        `hvac_modes` (DB-only), so this method reads each thermostat's
        live state via `get_thermostat_state` -- the only source of a
        real, current `hvac_modes` list -- before deciding to attempt,
        skip, or report unavailable."""
        rows = await self._thermostats.list_thermostats(home_id=home_id)
        results: list[dict[str, Any]] = []
        succeeded = failed = unavailable = skipped = 0
        for row in rows:
            try:
                live = await self._thermostats.get_thermostat_state(row["id"])
            except ServiceError as err:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": str(err),
                        "skipped": False,
                        "skip_reason": None,
                    }
                )
                failed += 1
                continue
            if not live["available"]:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": None,
                        "detail": "device unavailable",
                        "skipped": False,
                        "skip_reason": None,
                    }
                )
                unavailable += 1
                continue
            supported_modes = {str(mode).strip().lower() for mode in live["hvac_modes"]}
            if _ECO_HVAC_MODE not in supported_modes:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": None,
                        "detail": "skipped -- no eco-adjacent hvac_mode reported",
                        "skipped": True,
                        "skip_reason": "device does not report an eco-adjacent hvac_mode",
                    }
                )
                skipped += 1
                continue
            try:
                outcome = await self._thermostats.set_thermostat_state(
                    row["id"], hvac_mode=_ECO_HVAC_MODE
                )
            except ServiceError as err:
                results.append(
                    {
                        "device_id": row["id"],
                        "name": row["name"],
                        "success": False,
                        "detail": str(err),
                        "skipped": False,
                        "skip_reason": None,
                    }
                )
                failed += 1
                continue
            results.append(
                {
                    "device_id": row["id"],
                    "name": row["name"],
                    "success": outcome["success"],
                    "detail": outcome["detail"],
                    "skipped": False,
                    "skip_reason": None,
                }
            )
            if outcome["success"]:
                succeeded += 1
            else:
                failed += 1
        return results, succeeded, failed, unavailable, skipped

    def _build_action_result(
        self,
        *,
        home_id: str,
        mode: str,
        locks: list[dict[str, Any]],
        lights: list[dict[str, Any]],
        thermostats: list[dict[str, Any]],
        succeeded: int,
        failed: int,
        unavailable: int,
        skipped: int,
    ) -> dict[str, Any]:
        """Derives the overall status deterministically (Action Slice
        Logic Contract §6) -- never atomic, never a bare boolean."""
        requested = len(locks) + len(lights) + len(thermostats)
        attempted = succeeded + failed
        if requested == 0:
            status = "NO_TARGETS"
        elif failed == 0 and unavailable == 0:
            status = "SUCCESS"
        elif succeeded == 0:
            status = "FAILED"
        else:
            status = "PARTIAL_SUCCESS"
        return {
            "home_id": home_id,
            "mode": mode,
            "status": status,
            "locks": locks,
            "lights": lights,
            "thermostats": thermostats,
            "requested_count": requested,
            "attempted_count": attempted,
            "succeeded_count": succeeded,
            "failed_count": failed,
            "unavailable_count": unavailable,
            "skipped_count": skipped,
            "generated_at": datetime.now(UTC).isoformat(),
        }
