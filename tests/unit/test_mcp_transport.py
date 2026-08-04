"""Unit tests for the MCP transport abstraction -- Milestone 10.5 Task
Group A, deliverable 2."""

from __future__ import annotations

from typing import Any

import pytest

from jarvis.core.interfaces.mcp import IMCPTransport, MCPTransportError
from jarvis.core.mcp.transport import InProcessTransport, TransportFactoryRegistry


class _StubTransport:
    """Structural implementation -- no inheritance, matching how every
    other adapter in this codebase satisfies its port."""

    transport_type = "stdio"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"method": method}


def test_stub_satisfies_the_port_structurally() -> None:
    assert isinstance(_StubTransport({}), IMCPTransport)


def test_no_network_transport_is_registered_by_default() -> None:
    """Task Group A ships the abstraction, not the transports."""
    assert TransportFactoryRegistry().registered_types == ()


def test_register_then_create() -> None:
    registry = TransportFactoryRegistry()
    registry.register("stdio", _StubTransport)

    transport = registry.create("stdio", {"cmd": "server"})

    assert registry.registered_types == ("stdio",)
    assert registry.supports("stdio")
    assert transport.transport_type == "stdio"


def test_creating_an_unregistered_transport_raises() -> None:
    with pytest.raises(MCPTransportError, match="No transport registered"):
        TransportFactoryRegistry().create("websocket")


def test_registering_an_unknown_transport_type_raises() -> None:
    """The four future transport names are a fixed vocabulary, so a
    near-miss spelling fails loudly instead of registering silently."""
    with pytest.raises(MCPTransportError, match="Unknown transport type"):
        TransportFactoryRegistry().register("carrier_pigeon", _StubTransport)


def test_unregister_reports_whether_it_existed() -> None:
    registry = TransportFactoryRegistry()
    registry.register("http", _StubTransport)

    assert registry.unregister("http") is True
    assert registry.unregister("http") is False


# --- InProcessTransport ------------------------------------------------------


class _RecordingServer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    async def handle_request(
        self, method: str, params: dict[str, Any], *, client_id: str
    ) -> dict[str, Any]:
        self.calls.append((method, params, client_id))
        return {"ok": True}


@pytest.mark.asyncio
async def test_in_process_transport_dispatches_to_the_server() -> None:
    server = _RecordingServer()
    transport = InProcessTransport(server, client_id="c1")  # type: ignore[arg-type]

    await transport.connect()
    result = await transport.request("capabilities/list", {"kind": "tool"})

    assert result == {"ok": True}
    assert server.calls == [("capabilities/list", {"kind": "tool"}, "c1")]


@pytest.mark.asyncio
async def test_request_before_connect_raises() -> None:
    transport = InProcessTransport(_RecordingServer(), client_id="c1")  # type: ignore[arg-type]

    with pytest.raises(MCPTransportError, match="not connected"):
        await transport.request("initialize")


@pytest.mark.asyncio
async def test_connect_and_disconnect_are_idempotent() -> None:
    transport = InProcessTransport(_RecordingServer())  # type: ignore[arg-type]

    await transport.disconnect()  # never connected -- must not raise
    await transport.connect()
    await transport.connect()
    assert transport.is_connected is True

    await transport.disconnect()
    await transport.disconnect()
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_in_process_transport_satisfies_the_port() -> None:
    assert isinstance(InProcessTransport(_RecordingServer()), IMCPTransport)  # type: ignore[arg-type]
