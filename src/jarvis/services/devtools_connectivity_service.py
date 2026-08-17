"""Developer Tools -- Connectivity / Integration Health service.

Milestone 12 Developer Tools (Connectivity / Integration Health
Slice). `docs/M12_DEVELOPER_TOOLS_CONNECTIVITY_LOGIC_CONTRACT.md`
defines this module's entire contract: a **read-only aggregation**
over two already-shipped surfaces -- `ConnectorFactoryRegistry`/
`ConnectivityService` (connector registration/connection state) and
`SmartHomeService` (per-home device-health counts, via the
`HomeMetadata` aggregate Task Group A already built and no REST route
had used until now). Never a connector directly, never
`EventBus`, never a database of its own.

**Deliberately a `services/`-layer class, not a `core/devtools/`
component.** Every existing `core/devtools/*.py` component (
`DebugConsole`, `PerformanceProfiler`, `StateInspector`,
`ApiInspector`) depends only on other `core/`-layer objects --
importing `ConnectivityService`/`SmartHomeService` from `core/devtools/`
would invert this codebase's own core-to-services layering direction
(Logic Contract §5). This service's *route*, however, is added to the
existing `infrastructure/api/routes/devtools.py` file -- a
presentation-layer/URL-namespace choice, not a layering one.

**No `PermissionModel` gate, matching every one of M9's five existing
devtools capabilities exactly** (re-verified this session: none of
them has one). Session authentication (`Depends(get_current_session)`
at the route layer) is the only boundary -- a deliberate consistency
choice, not an oversight (Logic Contract §8).

**No fabricated telemetry.** Latency, uptime, reconnect counts, and
error counts are not tracked anywhere in `ConnectivityService` or
either connector -- none of them appear here. Only what
`ConnectorFactoryRegistry.registered_types`/`ConnectivityService.
is_connected`/`SmartHomeService.metadata` already compute is
returned.

**No secret exposure -- structurally, not by convention.** This
module never imports `ConnectorCredentialStore`, never reads
`Device.metadata_json`, and never touches a connector's own
configuration object. The only data it ever returns is connector
*type names* (strings), connection *booleans*, and *integer* device
counts -- there is no code path here through which a password, token,
API key, or MQTT credential could reach a response.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.services.connectivity_service import ConnectivityService
    from jarvis.services.smart_home_service import SmartHomeService


class DevtoolsConnectivityService:
    def __init__(
        self,
        *,
        connectivity: ConnectivityService,
        connectivity_registry: ConnectorFactoryRegistry,
        smart_home: SmartHomeService,
    ) -> None:
        self._connectivity = connectivity
        self._registry = connectivity_registry
        self._smart_home = smart_home

    # ------------------------------------------------------------------
    # Connector-level state (ungated -- Logic Contract §8)
    # ------------------------------------------------------------------
    async def get_connector_status(self) -> list[dict[str, Any]]:
        """One row per connector type with a registered factory
        (`ConnectorFactoryRegistry.registered_types`) -- including a
        registered-but-never-connected type, never silently omitted.
        `connected` re-checks the live connector object's own state
        (`ConnectivityService.is_connected`), not merely whether it
        appears in `connected_types`."""
        return [
            {
                "connector_type": connector_type,
                "registered": True,
                "connected": self._connectivity.is_connected(connector_type),
            }
            for connector_type in self._registry.registered_types
        ]

    # ------------------------------------------------------------------
    # Per-home device health (ungated -- Logic Contract §8)
    # ------------------------------------------------------------------
    async def get_device_health(self, home_id: str | None = None) -> list[dict[str, Any]]:
        """One `HomeMetadata` row for *home_id*, or one row per home
        (`SmartHomeService.list_homes`) when *home_id* is omitted.
        Propagates `SmartHomeService.metadata`'s own `ServiceError` for
        an unknown `home_id` -- not caught or re-wrapped here."""
        if home_id is not None:
            metadata = await self._smart_home.metadata(home_id)
            return [metadata.as_dict()]
        homes = await self._smart_home.list_homes()
        return [(await self._smart_home.metadata(home.id)).as_dict() for home in homes]

    # ------------------------------------------------------------------
    # Combined view -- the REST route's own single response shape
    # ------------------------------------------------------------------
    async def get_overview(self, home_id: str | None = None) -> dict[str, Any]:
        return {
            "connectors": await self.get_connector_status(),
            "homes": await self.get_device_health(home_id),
        }
