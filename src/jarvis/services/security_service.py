"""Security & Safety service -- Milestone 12 Security & Safety
(Read-Only Alert/Status Slice).

`docs/M12_SECURITY_SAFETY_LOGIC_CONTRACT.md` §13 defines this module's
entire contract: a **pull-based aggregation** over two already-shipped
services -- `SensorService` and `SmartLockService` -- never a connector,
never `ConnectivityService`/`SmartHomeService` directly. This module
owns no device category and adds no persistence.

**Every operation requires the `smart_home` permission for the new
`core:security` principal** -- independently of `SensorService`'s own
`core:sensors` grant (Logic Contract §3/§14). This module does not
catch or suppress a `SensorPermissionError` propagated from the nested
`SensorService` call; an operator who has not granted `core:sensors`
sees that failure surface honestly rather than a silently incomplete
"all clear" report.

**Alert semantics are closed and non-inferred** (Logic Contract §4):
only `smoke`/`gas`/`moisture` (water leak) -- HA's own literal
"hazard detected" `device_class` values -- can become an active alert.
`door`/`window`/`garage_door`/`motion`/`presence`/`occupancy`/
`vibration` and lock state are always reported as factual status only;
none of them is ever elevated to an alert or allowed to move
`overall_status`. This is a structural invariant, not a per-case
judgment call.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError

if TYPE_CHECKING:
    from jarvis.core.plugins.permissions import PermissionModel
    from jarvis.services.sensor_service import SensorService
    from jarvis.services.smart_lock_service import SmartLockService

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
        permissions: PermissionModel,
    ) -> None:
        self._sensors = sensors
        self._smart_lock = smart_lock
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
