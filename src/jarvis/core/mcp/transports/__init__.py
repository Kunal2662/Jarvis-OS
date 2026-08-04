"""Concrete MCP transports -- Milestone 10.5 Task Group B.

Task Group A shipped the ``IMCPTransport`` port and the factory registry
seam; this package fills that seam with the four real transports the
milestone names -- ``stdio``, ``websocket``, ``http`` and ``ipc`` --
plus the shared JSON-RPC framing two of them reuse.

Nothing here duplicates Task Group A: connection retry, handshake,
capability discovery and negotiation all remain
``MCPClientRuntime``'s job, and permission enforcement remains
``MCPServerRuntime``'s. A transport's whole responsibility is to move
one JSON-RPC request and return its response.
"""

from __future__ import annotations

from jarvis.core.mcp.transports.factory import (
    build_default_transport_registry,
    build_http_transport,
    build_ipc_transport,
    build_stdio_transport,
    build_websocket_transport,
)
from jarvis.core.mcp.transports.http import HttpTransport
from jarvis.core.mcp.transports.ipc import IpcTransport
from jarvis.core.mcp.transports.jsonrpc import JsonRpcStreamChannel
from jarvis.core.mcp.transports.stdio import StdioTransport
from jarvis.core.mcp.transports.websocket import WebSocketTransport

__all__ = [
    "HttpTransport",
    "IpcTransport",
    "JsonRpcStreamChannel",
    "StdioTransport",
    "WebSocketTransport",
    "build_default_transport_registry",
    "build_http_transport",
    "build_ipc_transport",
    "build_stdio_transport",
    "build_websocket_transport",
]
