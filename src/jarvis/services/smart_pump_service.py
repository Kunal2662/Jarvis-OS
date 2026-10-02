"""Smart Pump service -- Milestone 12 Smart Pumps (Switch-Backed Device
Slice).

**A pump has no device type of its own, by deliberate scope decision.**
In this data model a pump *is* a ``device_type="switch"`` row -- a
relay/plug controlling a water pump, sump pump, pool pump, irrigation
pump feed, etc. This service is the thin pump-flavored semantic layer
over that row: pump-identity validation plus delegation. It never
re-implements command translation, permission enforcement or the
``ConnectivityService.send_command`` chokepoint -- those all live in
:class:`~jarvis.services.smart_switch_service.SmartSwitchService` and
are reached by composition, per the preferred "existing switch device ->
pump service abstraction" over "new pump device type" direction.

**Pump identity is role, not type.** ``_require_pump`` accepts any
switch-backed device; there is no ``pump`` marker field (``UpdateDevice``
does not accept metadata, and no setter exists), so which switches are
physically pumps stays a deployment fact (naming/room/grouping), not a
schema fact. Every response this service returns carries
``kind: "pump"`` so callers can tell a pump-surface response from a bare
switch-surface one.

**Confirmation is agent-tool-level, not service-level.** ``pump_on`` /
``pump_off`` are added to ``AgentSettings.confirm_required_tools`` (both
directions -- see that setting's comment), enforced exclusively by
``agents/permission.py``'s ``AgentPermissionGate`` at the agent-tool
boundary. This service itself performs no confirmation, exactly like
``SirenService``/``SmartLockService``; the REST surface likewise has no
confirmation concept (see ``routes/pumps.py``). No per-device
``safety_critical`` enforcement exists anywhere in this repository, and
this module does not pretend otherwise.

**Permission is inherited, not re-declared.** No new principal: every
mutation below is validated by the delegated ``SmartSwitchService``'s
own ``core:smart_switch`` grant under the shared ``smart_home`` scope.
Reads are ungated, inheriting the switch read precedent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError

if TYPE_CHECKING:
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.smart_switch_service import SmartSwitchService

#: The only device type a pump may be backed by -- the same constant
#: ``smart_switch_service`` validates against; a pump never exists as
#: anything else in this model.
_SWITCH_DEVICE_TYPE = "switch"


class SmartPumpService:
    def __init__(
        self,
        *,
        switches: SmartSwitchService,
        smart_home: SmartHomeService,
    ) -> None:
        self._switches = switches
        self._smart_home = smart_home

    # ------------------------------------------------------------------
    # Pump identity
    # ------------------------------------------------------------------
    async def _require_pump(self, device_id: str) -> Device:
        """Resolves the underlying switch-backed device and validates it
        is pump-controllable.

        Runs *before* the delegated permission check deliberately: device
        existence and type are already readable by any authenticated
        session through the ungated ``GET /switches/{id}`` state path, so
        this ordering reveals nothing that surface does not. The delegated
        ``SmartSwitchService`` then enforces ``core:smart_switch`` on
        every mutation -- permission is never skipped, only ordered
        after identity validation.
        """
        device = await self._smart_home.require_device(device_id)
        if device.device_type != _SWITCH_DEVICE_TYPE:
            raise ServiceError(
                f"Device {device_id!r} is a {device.device_type!r}, not a pump: "
                "smart pumps are switch-backed devices."
            )
        return device

    # ------------------------------------------------------------------
    # Reads (ungated -- inherits the switch read precedent)
    # ------------------------------------------------------------------
    async def get_state(self, device_id: str) -> dict[str, Any]:
        await self._require_pump(device_id)
        # Delegated read: same live-state merge / DB-fallback behavior
        # `SmartSwitchService.get_switch_state` already provides. That
        # call re-resolves the device through its own `_require_switch`;
        # the deliberate double read keeps SmartSwitchService untouched.
        state = await self._switches.get_switch_state(device_id)
        return {**state, "kind": "pump"}

    # ------------------------------------------------------------------
    # Commands (permission + translation + chokepoint all delegated)
    # ------------------------------------------------------------------
    async def turn_on(self, device_id: str) -> dict[str, Any]:
        await self._require_pump(device_id)
        result = await self._switches.turn_on(device_id)
        return {**result, "kind": "pump"}

    async def turn_off(self, device_id: str) -> dict[str, Any]:
        await self._require_pump(device_id)
        result = await self._switches.turn_off(device_id)
        return {**result, "kind": "pump"}
