"""Transport lifecycle tests against **real** peers -- Milestone 10.5
Task Group B, deliverables 1-4.

A real subprocess for stdio, a real ``websockets`` server for
WebSocket, a real HTTP server for HTTP. The transports' entire job is
process/socket lifecycle plus framing, and a stubbed peer exercises
neither -- so these use the genuine article and are correspondingly
worth having.

The IPC transport is covered separately in
``test_mcp_transport_ipc.py``, which needs a platform-specific server.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.mcp.transports.http import HttpTransport
from jarvis.core.mcp.transports.stdio import StdioTransport
from jarvis.core.mcp.transports.websocket import WebSocketTransport

_PEER_SCRIPT = str(Path(__file__).resolve().parents[1] / "fixtures" / "mcp_stdio_peer.py")

_CAPABILITIES = [
    {"name": "echo", "kind": "tool", "permissions": ["agent_tools"]},
    {"name": "read_secret", "kind": "tool", "permissions": ["filesystem"]},
]


def _peer_response(message: dict) -> dict:
    method = message.get("method")
    params = message.get("params") or {}
    if method == "initialize":
        return {"server_id": "peer", "agreed_version": "2025-06-18"}
    if method == "capabilities/list":
        return {"capabilities": _CAPABILITIES}
    if method == "capabilities/call":
        return {"result": {"echoed": params.get("arguments", {}).get("text", "")}}
    if method == "ping":
        return {"pong": True}
    raise ValueError(f"unknown method {method!r}")


# --- stdio --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdio_connects_to_a_real_subprocess() -> None:
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT])
    try:
        await transport.connect()

        assert transport.is_connected is True
        assert transport.pid is not None
        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_stdio_disconnect_terminates_the_child() -> None:
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT])
    await transport.connect()

    await transport.disconnect()

    assert transport.is_connected is False
    assert transport.pid is None


@pytest.mark.asyncio
async def test_stdio_connect_is_idempotent_and_does_not_orphan() -> None:
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT])
    try:
        await transport.connect()
        first_pid = transport.pid
        await transport.connect()

        assert transport.pid == first_pid
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_stdio_disconnect_is_safe_before_connect() -> None:
    await StdioTransport(sys.executable, [_PEER_SCRIPT]).disconnect()


@pytest.mark.asyncio
async def test_stdio_request_before_connect_is_refused() -> None:
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT])
    with pytest.raises(MCPTransportError, match="not connected"):
        await transport.request("ping")


@pytest.mark.asyncio
async def test_stdio_reports_a_peer_error_without_dying() -> None:
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT])
    try:
        await transport.connect()

        with pytest.raises(MCPTransportError, match="peer error"):
            await transport.request("no/such/method")

        # The channel survives a peer-level error.
        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_stdio_missing_executable_fails_loudly() -> None:
    transport = StdioTransport("definitely-not-a-real-binary-xyz")
    with pytest.raises(MCPTransportError, match="cannot start"):
        await transport.connect()


def test_stdio_requires_a_command() -> None:
    with pytest.raises(MCPTransportError, match="command"):
        StdioTransport("")


@pytest.mark.asyncio
async def test_stdio_detects_a_dead_peer() -> None:
    """The peer exits after one request; the transport must report
    itself disconnected rather than pretending the channel is live."""
    transport = StdioTransport(sys.executable, [_PEER_SCRIPT, "--exit-after", "1"])
    try:
        await transport.connect()
        await transport.request("ping")
        await asyncio.sleep(0.3)

        assert transport.is_connected is False
    finally:
        await transport.disconnect()


# --- websocket ----------------------------------------------------------------


@pytest.fixture
async def ws_server():
    from websockets.asyncio.server import serve

    async def handler(connection) -> None:
        async for raw in connection:
            message = json.loads(raw)
            try:
                payload = {"jsonrpc": "2.0", "id": message["id"], "result": _peer_response(message)}
            except ValueError as err:
                payload = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": str(err)},
                }
            await connection.send(json.dumps(payload))

    async with serve(handler, "127.0.0.1", 0) as server:
        port = next(iter(server.sockets)).getsockname()[1]
        yield f"ws://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_websocket_round_trip(ws_server: str) -> None:
    transport = WebSocketTransport(ws_server)
    try:
        await transport.connect()

        assert transport.is_connected is True
        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_websocket_handles_concurrent_requests(ws_server: str) -> None:
    transport = WebSocketTransport(ws_server)
    try:
        await transport.connect()
        results = await asyncio.gather(*(transport.request("ping") for _ in range(10)))

        assert all(r["pong"] for r in results)
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_websocket_disconnect_is_idempotent(ws_server: str) -> None:
    transport = WebSocketTransport(ws_server)
    await transport.connect()
    await transport.disconnect()
    await transport.disconnect()

    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_websocket_unreachable_host_fails() -> None:
    transport = WebSocketTransport("ws://127.0.0.1:9/nothing")
    with pytest.raises(MCPTransportError, match="cannot connect"):
        await transport.connect()
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_websocket_request_before_connect_is_refused(ws_server: str) -> None:
    with pytest.raises(MCPTransportError, match="not connected"):
        await WebSocketTransport(ws_server).request("ping")


def test_websocket_requires_a_url() -> None:
    with pytest.raises(MCPTransportError, match="url"):
        WebSocketTransport("")


# --- http ---------------------------------------------------------------------


@pytest.fixture
def http_server():
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # silence the test log
            return

        def do_POST(self) -> None:
            length = int(self.headers["Content-Length"])
            message = json.loads(self.rfile.read(length))
            try:
                payload = {"jsonrpc": "2.0", "id": message["id"], "result": _peer_response(message)}
            except ValueError as err:
                payload = {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "error": {"code": -32601, "message": str(err)},
                }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/mcp"
    server.shutdown()


@pytest.mark.asyncio
async def test_http_round_trip(http_server: str) -> None:
    transport = HttpTransport(http_server)
    try:
        await transport.connect()

        assert transport.is_connected is True
        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_http_unreachable_host_fails_connect(http_server: str) -> None:
    """The regression this guards: ``connect`` used to route its probe
    through ``request``, which wraps every httpx failure as
    ``MCPTransportError`` -- so an unreachable host was swallowed and
    the transport reported itself connected."""
    transport = HttpTransport("http://127.0.0.1:9/nothing")

    with pytest.raises(MCPTransportError, match="cannot reach"):
        await transport.connect()
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_http_peer_error_is_reported(http_server: str) -> None:
    transport = HttpTransport(http_server)
    try:
        await transport.connect()
        with pytest.raises(MCPTransportError, match="peer error"):
            await transport.request("no/such/method")
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_http_request_before_connect_is_refused(http_server: str) -> None:
    with pytest.raises(MCPTransportError, match="not connected"):
        await HttpTransport(http_server).request("ping")


@pytest.mark.asyncio
async def test_http_disconnect_is_idempotent(http_server: str) -> None:
    transport = HttpTransport(http_server)
    await transport.connect()
    await transport.disconnect()
    await transport.disconnect()

    assert transport.is_connected is False


def test_http_requires_a_url() -> None:
    with pytest.raises(MCPTransportError, match="url"):
        HttpTransport("")
