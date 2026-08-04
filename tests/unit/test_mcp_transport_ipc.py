"""IPC transport tests -- Milestone 10.5 Task Group B, deliverable 4.

Split from ``test_mcp_transports_live.py`` because the *server* side is
genuinely platform-specific: a Windows named pipe needs the Proactor
loop's ``start_serving_pipe``, a POSIX peer needs
``asyncio.start_unix_server``. The transport under test is one class
with one branch; only the fixture differs.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid

import pytest

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.mcp.transports.ipc import IpcTransport, default_endpoint_prefix


def _respond(message: dict) -> dict:
    method = message.get("method")
    if method == "initialize":
        return {"server_id": "ipc-peer", "agreed_version": "2025-06-18"}
    if method == "capabilities/list":
        return {"capabilities": [{"name": "echo", "kind": "tool", "permissions": []}]}
    if method == "ping":
        return {"pong": True}
    return {"ok": True}


async def _serve(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        line = await reader.readline()
        if not line:
            return
        message = json.loads(line)
        payload = {"jsonrpc": "2.0", "id": message.get("id"), "result": _respond(message)}
        writer.write((json.dumps(payload) + "\n").encode())
        await writer.drain()


@pytest.fixture
async def ipc_endpoint(tmp_path):
    """A real local endpoint: a named pipe on Windows, a Unix socket
    elsewhere."""
    if sys.platform == "win32":
        endpoint = rf"\\.\pipe\jarvis-mcp-test-{uuid.uuid4().hex[:8]}"
        loop = asyncio.get_running_loop()

        def factory() -> asyncio.StreamReaderProtocol:
            reader = asyncio.StreamReader(loop=loop)
            return asyncio.StreamReaderProtocol(
                reader, lambda r, w: asyncio.ensure_future(_serve(r, w)), loop=loop
            )

        start_serving_pipe = getattr(loop, "start_serving_pipe", None)
        if start_serving_pipe is None:
            pytest.skip("named pipes require the Proactor event loop")
        servers = await start_serving_pipe(factory, endpoint)
        yield endpoint
        for server in servers:
            server.close()
    else:
        endpoint = str(tmp_path / "mcp.sock")
        server = await asyncio.start_unix_server(_serve, path=endpoint)
        yield endpoint
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_ipc_round_trip_over_a_real_local_endpoint(ipc_endpoint: str) -> None:
    transport = IpcTransport(ipc_endpoint)
    try:
        await transport.connect()

        assert transport.is_connected is True
        assert transport.transport_type == "ipc"
        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_ipc_disconnect_is_idempotent(ipc_endpoint: str) -> None:
    transport = IpcTransport(ipc_endpoint)
    await transport.connect()
    await transport.disconnect()
    await transport.disconnect()

    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_ipc_reconnect_after_disconnect(ipc_endpoint: str) -> None:
    transport = IpcTransport(ipc_endpoint)
    try:
        await transport.connect()
        await transport.disconnect()
        await transport.connect()

        assert (await transport.request("ping"))["pong"] is True
    finally:
        await transport.disconnect()


@pytest.mark.asyncio
async def test_ipc_unknown_endpoint_fails_loudly() -> None:
    missing = (
        r"\\.\pipe\jarvis-mcp-does-not-exist-xyz"
        if sys.platform == "win32"
        else "/tmp/jarvis-mcp-does-not-exist-xyz.sock"
    )
    transport = IpcTransport(missing)

    with pytest.raises(MCPTransportError, match="cannot connect"):
        await transport.connect()
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_ipc_request_before_connect_is_refused() -> None:
    with pytest.raises(MCPTransportError, match="not connected"):
        await IpcTransport("some-endpoint").request("ping")


def test_ipc_requires_an_endpoint() -> None:
    with pytest.raises(MCPTransportError, match="endpoint"):
        IpcTransport("")


def test_default_endpoint_prefix_matches_the_platform() -> None:
    prefix = default_endpoint_prefix()
    assert prefix == (r"\\.\pipe" if sys.platform == "win32" else "/tmp")
