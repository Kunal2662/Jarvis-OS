"""MCP platform -- Milestone 10.5 Task Group A (core runtime).

The protocol-and-registry layer beneath M11: capability registry,
transport abstraction, client/server lifecycles, and negotiation.
Provider integrations, OAuth, and cloud sync are M11's own scope and
are deliberately absent here -- see ``docs/MASTER_ROADMAP.md`` section 8's
M10.5 entry.

Lives in ``core/`` alongside ``core/plugins/`` rather than in
``services/`` because it is runtime infrastructure with a lifecycle,
not an application service -- the same placement decision
``core/plugins/`` and ``core/lifecycle/`` already reflect.
"""

from __future__ import annotations

from jarvis.core.mcp.capabilities import MCPCapabilityRegistry
from jarvis.core.mcp.client import MCPClientRuntime, MCPConnectionState
from jarvis.core.mcp.negotiation import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    NegotiationResult,
    negotiate,
    negotiate_version,
)
from jarvis.core.mcp.server import MCPServerRuntime
from jarvis.core.mcp.transport import InProcessTransport, TransportFactoryRegistry

__all__ = [
    "PROTOCOL_VERSION",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "InProcessTransport",
    "MCPCapabilityRegistry",
    "MCPClientRuntime",
    "MCPConnectionState",
    "MCPServerRuntime",
    "NegotiationResult",
    "TransportFactoryRegistry",
    "negotiate",
    "negotiate_version",
]
