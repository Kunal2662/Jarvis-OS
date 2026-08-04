"""MCP Provider Framework -- Milestone 10.5 Task Group C.

Infrastructure only: the generic framework every future MCP integration
plugs into **without modifying the MCP runtime**. No real providers ship
here, and no OAuth, authentication, or vendor-specific code -- those are
Task Group D and M11.

The split is deliberate and mirrors ``core/plugins/``'s own:

- ``metadata.py`` -- what a provider *is* and how it should *run*
  (inert data, validated at registration).
- ``registry.py`` -- what providers *exist* (declaration, lookup,
  discovery). Registration has no side effects.
- ``manager.py`` -- what providers are *doing* (lifecycle, events,
  health collection, permission resolution).
- ``transport_backed.py`` -- the generic implementation that covers
  every "point at an MCP server with this transport config" case.

Nothing here re-implements connection management, permissions, or
health: those delegate to ``MCPClientRuntime`` (Task Group A),
``PermissionModel`` (M9), and ``HealthMonitor`` (M9) respectively.
"""

from __future__ import annotations

from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.metadata import (
    PROVIDER_ACTIONS,
    HeartbeatSettings,
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
    ReconnectPolicy,
    RetryPolicy,
)
from jarvis.core.mcp.providers.registry import MCPProviderRegistry, ProviderRecord
from jarvis.core.mcp.providers.transport_backed import TransportBackedProvider

__all__ = [
    "PROVIDER_ACTIONS",
    "HeartbeatSettings",
    "MCPProviderError",
    "MCPProviderManager",
    "MCPProviderRegistry",
    "ProviderConfig",
    "ProviderMetadata",
    "ProviderRecord",
    "ProviderState",
    "ReconnectPolicy",
    "RetryPolicy",
    "TransportBackedProvider",
]
