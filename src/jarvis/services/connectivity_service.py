"""Connectivity service -- Milestone 12 Task Group B, Phase 1.

Owns connector lifecycle and is the *only* caller of
``SmartHomeService`` for state changes that originate from real
hardware -- Task Group A's own REST-driven ``pair_device``/
``update_device`` remain the human-initiated path; this is the
machine-initiated one. Both converge on the same service, never two
write paths to the same table.

**No protocol code here.** This module resolves a connector through
``ConnectorFactoryRegistry`` and calls only the five
``IDeviceConnector`` methods -- it does not know or care whether a
connector talks to Home Assistant, MQTT, or anything else. That is the
entire point of the port/adapter split this task group's Logic
Contract describes.

**Discovery is idempotent by home + external id, not by Device row.**
``SmartHomeService.register_discovered_device`` itself is a plain
create (deliberately, so a manual "add a device I know about" caller
is never silently turned into a no-op) -- this service is what checks
``get_device_by_external_id`` first, so a connector's own repeated
discovery polls do not create a new row every time they see the same
physical device.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.connectivity import ConnectorNotConnectedError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.connectivity import CommandResult, IDeviceConnector
    from jarvis.infrastructure.database.models import Device
    from jarvis.services.smart_home_service import SmartHomeService

_logger = get_logger("jarvis.services.connectivity")

#: A connector's own reported status string is not one of
#: ``DEVICE_STATUSES`` -- this maps the common shapes a real connector
#: is likely to report onto the closed vocabulary
#: ``SmartHomeService.report_device_state`` enforces. Deliberately
#: small and provisional: Phase 2's real Home Assistant connector is
#: what will prove or revise this mapping against real state strings,
#: not a guess made without one.
_ONLINE_STATUS_HINTS = frozenset({"on", "off", "online", "available", "active", "idle"})
_OFFLINE_STATUS_HINTS = frozenset({"offline", "unavailable"})


def _map_connector_status(raw_status: str) -> str:
    normalized = raw_status.strip().lower()
    if normalized in _ONLINE_STATUS_HINTS:
        return "paired"
    if normalized in _OFFLINE_STATUS_HINTS:
        return "offline"
    return "unreachable"


class ConnectivityService:
    def __init__(
        self,
        *,
        registry: ConnectorFactoryRegistry,
        smart_home: SmartHomeService,
        event_bus: EventBus | None = None,
    ) -> None:
        self._registry = registry
        self._smart_home = smart_home
        self._event_bus = event_bus
        self._connectors: dict[str, IDeviceConnector] = {}

    # ------------------------------------------------------------------
    # Connector lifecycle
    # ------------------------------------------------------------------
    @property
    def connected_types(self) -> tuple[str, ...]:
        return tuple(sorted(self._connectors))

    def is_connected(self, connector_type: str) -> bool:
        connector = self._connectors.get(connector_type)
        return connector is not None and connector.is_connected

    async def connect(self, connector_type: str, config: dict[str, Any] | None = None) -> None:
        """Idempotent -- connecting an already-connected type reconnects
        the existing instance rather than leaking a second one, the
        same idempotency `IDeviceConnector.connect` itself promises."""
        await self._publish_status(connector_type, status="connecting")
        connector = self._connectors.get(connector_type)
        if connector is None:
            connector = self._registry.create(connector_type, config)
            self._connectors[connector_type] = connector
        await connector.connect()
        await self._publish_status(connector_type, status="connected")

    async def disconnect(self, connector_type: str) -> None:
        connector = self._connectors.get(connector_type)
        if connector is None:
            return
        await self._publish_status(connector_type, status="disconnecting")
        await connector.disconnect()
        del self._connectors[connector_type]
        await self._publish_status(connector_type, status="disconnected")

    def _require_connector(self, connector_type: str) -> IDeviceConnector:
        connector = self._connectors.get(connector_type)
        if connector is None or not connector.is_connected:
            raise ConnectorNotConnectedError(
                f"Connector {connector_type!r} is not connected. "
                f"Connected: {self.connected_types or 'none'}."
            )
        return connector

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    async def run_discovery(self, connector_type: str, home_id: str) -> list[Device]:
        """Discovers devices through *connector_type* and registers
        every genuinely new one with `SmartHomeService`. An
        already-known device (matched on home + external id) is left
        as-is -- **not** updated by this method; see
        `refresh_device_state` for the real-state-driven update path.
        Returns every `Device` this run touched, new or already-known.
        """
        connector = self._require_connector(connector_type)
        found = await connector.discover()
        devices: list[Device] = []
        for candidate in found:
            existing = await self._smart_home.get_device_by_external_id(
                home_id, candidate.external_id
            )
            if existing is not None:
                devices.append(existing)
                continue
            registered = await self._smart_home.register_discovered_device(
                home_id,
                candidate.name,
                device_type=candidate.device_type,
                manufacturer=candidate.manufacturer,
                model=candidate.model,
                external_id=candidate.external_id,
                metadata={"connector_type": connector_type, **candidate.metadata},
            )
            devices.append(registered)
        _logger.info(
            "Discovery via {} found {} device(s), {} new.",
            connector_type,
            len(found),
            sum(1 for d in devices if d.status == "discovered"),
        )
        return devices

    # ------------------------------------------------------------------
    # State + commands
    # ------------------------------------------------------------------
    async def refresh_device_state(self, device_id: str) -> Device | None:
        """Reads a device's real state through whichever connector
        discovered it, and drives `SmartHomeService.report_device_state`
        with the result -- the first real data
        `HomeMetadata.offline_device_count`/`unreachable_device_count`
        have had since Task Group A defined them."""
        device = await self._smart_home.get_device(device_id)
        if device is None or not device.external_id:
            return None
        connector_type = self._connector_type_for(device)
        if connector_type is None:
            return None
        connector = self._require_connector(connector_type)
        state = await connector.read_state(device.external_id)
        mapped = _map_connector_status(state.status)
        return await self._smart_home.report_device_state(device_id, status=mapped)

    async def send_command(
        self, device_id: str, command: str, payload: dict[str, Any] | None = None
    ) -> CommandResult:
        """The single chokepoint a later M12 module (Home Automation /
        AI Home Assistant) gates for `safety_critical` devices -- see
        this task group's Logic Contract. Nothing in this method
        interprets what *command* means; it only routes it to the
        connector that owns the device.
        """
        device = await self._smart_home.require_device(device_id)
        connector_type = self._connector_type_for(device)
        if connector_type is None:
            raise ConnectorNotConnectedError(
                f"Device {device_id!r} has no recorded connector; it cannot be commanded."
            )
        connector = self._require_connector(connector_type)
        return await connector.send_command(device.external_id or "", command, payload or {})

    @staticmethod
    def _connector_type_for(device: Device) -> str | None:
        try:
            metadata = json.loads(device.metadata_json or "{}")
        except (TypeError, ValueError):
            return None
        value = metadata.get("connector_type")
        return str(value) if value else None

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def _publish_status(self, connector_type: str, *, status: str, detail: str = "") -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import ConnectivityStatusChangedEvent

        await self._event_bus.publish(
            ConnectivityStatusChangedEvent(
                connector_type=connector_type, status=status, detail=detail
            )
        )
