"""Unit tests for the MCP Client Runtime -- Milestone 10.5 Task Group A,
deliverable 3 (connection management, handshake, discovery, health,
reconnect)."""

from __future__ import annotations

from typing import Any

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import MCPConnectionChangedEvent
from jarvis.core.interfaces.mcp import MCPError, MCPTransportError
from jarvis.core.mcp.client import MCPClientRuntime, MCPConnectionState
from jarvis.core.mcp.negotiation import SUPPORTED_PROTOCOL_VERSIONS


class _FakeTransport:
    """A scriptable peer -- the fake for the ``IMCPTransport`` port, per
    this project's own "every new port ships with a fake" rule."""

    transport_type = "in_process"

    def __init__(
        self,
        *,
        capabilities: list[dict[str, Any]] | None = None,
        versions: list[str] | None = None,
        fail_connect_times: int = 0,
        fail_on_disconnect: bool = False,
    ) -> None:
        self._capabilities = capabilities if capabilities is not None else []
        self._versions = versions if versions is not None else list(SUPPORTED_PROTOCOL_VERSIONS)
        self._fail_connect_times = fail_connect_times
        self._fail_on_disconnect = fail_on_disconnect
        self._connected = False
        self.connect_attempts = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self.connect_attempts += 1
        if self._fail_connect_times >= self.connect_attempts:
            raise MCPTransportError("connect refused")
        self._connected = True

    async def disconnect(self) -> None:
        if self._fail_on_disconnect:
            raise MCPTransportError("teardown blew up")
        self._connected = False

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        self.calls.append((method, params or {}))
        if method == "initialize":
            shared = [v for v in self._versions if v in SUPPORTED_PROTOCOL_VERSIONS]
            return {
                "server_id": "peer",
                "agreed_version": shared[0] if shared else "",
                "failure_reason": "" if shared else "No shared protocol version.",
            }
        if method == "capabilities/list":
            return {"capabilities": self._capabilities}
        if method == "capabilities/call":
            return {"result": {"called": (params or {}).get("name")}}
        raise MCPTransportError(f"unknown method {method}")


def _cap(name: str, permissions: tuple[str, ...] = ()) -> dict[str, Any]:
    return {"name": name, "kind": "tool", "permissions": list(permissions)}


# --- Registration ------------------------------------------------------------


def test_registering_does_not_connect() -> None:
    """A configured-but-offline peer stays visible rather than being
    invisible until it happens to be reachable."""
    client = MCPClientRuntime()
    connection = client.register_connection("peer", _FakeTransport())

    assert connection.state is MCPConnectionState.DISCONNECTED
    assert client.server_ids == ("peer",)
    assert client.snapshot()[0]["state"] == "disconnected"


@pytest.mark.asyncio
async def test_connecting_an_unregistered_server_raises() -> None:
    with pytest.raises(MCPError, match="not registered"):
        await MCPClientRuntime().connect("nope")


# --- Handshake + discovery ----------------------------------------------------


@pytest.mark.asyncio
async def test_connect_performs_handshake_then_discovery() -> None:
    transport = _FakeTransport(capabilities=[_cap("echo")])
    client = MCPClientRuntime()
    client.register_connection("peer", transport)

    assert await client.connect("peer") is True

    connection = client.get("peer")
    assert connection is not None
    assert connection.state is MCPConnectionState.CONNECTED
    assert connection.agreed_version == SUPPORTED_PROTOCOL_VERSIONS[0]
    assert connection.capabilities.names == ("echo",)
    assert [m for m, _ in transport.calls] == ["initialize", "capabilities/list"]


@pytest.mark.asyncio
async def test_version_mismatch_fails_the_connection_without_raising() -> None:
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(versions=["1999-01-01"]))

    assert await client.connect("peer") is False

    connection = client.get("peer")
    assert connection is not None
    assert connection.state is MCPConnectionState.FAILED
    assert "No shared protocol version" in connection.error


@pytest.mark.asyncio
async def test_ungranted_capabilities_are_rejected_but_connection_succeeds() -> None:
    client = MCPClientRuntime()
    client.register_connection(
        "peer",
        _FakeTransport(
            capabilities=[_cap("allowed", ("agent_tools",)), _cap("blocked", ("network",))]
        ),
    )

    assert await client.connect("peer", granted_scopes={"agent_tools"}) is True

    connection = client.get("peer")
    assert connection is not None
    assert connection.capabilities.names == ("allowed",)
    assert [name for name, _ in connection.rejected] == ["blocked"]


# --- Reconnect ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_without_retry_gives_up_after_one_attempt() -> None:
    transport = _FakeTransport(fail_connect_times=1)
    client = MCPClientRuntime()
    client.register_connection("peer", transport)

    assert await client.connect("peer") is False
    assert transport.connect_attempts == 1


@pytest.mark.asyncio
async def test_retry_recovers_from_a_transient_failure() -> None:
    transport = _FakeTransport(fail_connect_times=2, capabilities=[_cap("echo")])
    client = MCPClientRuntime(reconnect_attempts=3, reconnect_backoff_seconds=0.0)
    client.register_connection("peer", transport)

    assert await client.connect("peer", retry=True) is True
    assert transport.connect_attempts == 3


@pytest.mark.asyncio
async def test_retry_exhausts_and_records_the_last_error() -> None:
    transport = _FakeTransport(fail_connect_times=99)
    client = MCPClientRuntime(reconnect_attempts=2, reconnect_backoff_seconds=0.0)
    client.register_connection("peer", transport)

    assert await client.connect("peer", retry=True) is False
    connection = client.get("peer")
    assert connection is not None
    assert connection.state is MCPConnectionState.FAILED
    assert "connect refused" in connection.error


@pytest.mark.asyncio
async def test_reconnect_disconnects_then_connects() -> None:
    transport = _FakeTransport(capabilities=[_cap("echo")])
    client = MCPClientRuntime(reconnect_backoff_seconds=0.0)
    client.register_connection("peer", transport)
    await client.connect("peer")

    assert await client.reconnect("peer") is True
    assert transport.connect_attempts == 2


# --- Disconnect ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_clears_stale_capabilities() -> None:
    """A stale capability list is worse than an empty one -- callers
    would otherwise negotiate against capabilities nothing serves."""
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(capabilities=[_cap("echo")]))
    await client.connect("peer")

    assert await client.disconnect("peer") is True

    connection = client.get("peer")
    assert connection is not None
    assert connection.state is MCPConnectionState.DISCONNECTED
    assert connection.capabilities.names == ()
    assert connection.agreed_version == ""


@pytest.mark.asyncio
async def test_disconnecting_an_unknown_server_returns_false() -> None:
    assert await MCPClientRuntime().disconnect("nope") is False


@pytest.mark.asyncio
async def test_a_failing_teardown_does_not_mask_the_result() -> None:
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(fail_on_disconnect=True))
    await client.connect("peer")

    assert await client.disconnect("peer") is True


@pytest.mark.asyncio
async def test_disconnect_all_covers_every_connection() -> None:
    client = MCPClientRuntime()
    client.register_connection("a", _FakeTransport())
    client.register_connection("b", _FakeTransport())
    await client.connect("a")
    await client.connect("b")

    await client.disconnect_all()

    assert all(c["state"] == "disconnected" for c in client.snapshot())


# --- Invocation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_reaches_the_peer() -> None:
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(capabilities=[_cap("echo")]))
    await client.connect("peer")

    assert await client.call("peer", "echo", {"text": "hi"}) == {"result": {"called": "echo"}}


@pytest.mark.asyncio
async def test_call_before_connect_is_refused() -> None:
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(capabilities=[_cap("echo")]))

    with pytest.raises(MCPError, match="not connected"):
        await client.call("peer", "echo")


@pytest.mark.asyncio
async def test_call_of_a_non_negotiated_capability_is_refused() -> None:
    """Not merely "unknown" -- it was explicitly dropped by negotiation,
    so calling it must fail client-side rather than reach the peer."""
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport(capabilities=[_cap("blocked", ("network",))]))
    await client.connect("peer", granted_scopes=set())

    with pytest.raises(MCPError, match="was not negotiated"):
        await client.call("peer", "blocked")


# --- Re-negotiation, health, events -------------------------------------------


@pytest.mark.asyncio
async def test_negotiated_recomputes_without_a_round_trip() -> None:
    transport = _FakeTransport(capabilities=[_cap("echo", ("agent_tools",))])
    client = MCPClientRuntime()
    client.register_connection("peer", transport)
    await client.connect("peer", granted_scopes={"agent_tools"})
    calls_before = len(transport.calls)

    result = await client.negotiated("peer", granted_scopes={"agent_tools"})

    assert result.succeeded is True
    assert result.capability_names == ("echo",)
    assert len(transport.calls) == calls_before


@pytest.mark.asyncio
async def test_health_is_unhealthy_only_when_a_connection_failed() -> None:
    client = MCPClientRuntime()
    assert (await client.health()).healthy is True

    client.register_connection("peer", _FakeTransport(versions=["1999-01-01"]))
    await client.connect("peer")

    health = await client.health()
    assert health.healthy is False
    assert "peer" in health.detail


@pytest.mark.asyncio
async def test_status_lists_connected_peers() -> None:
    client = MCPClientRuntime()
    client.register_connection("peer", _FakeTransport())
    await client.connect("peer")

    status = await client.status()

    assert status.state == "running"
    assert status.detail["connected"] == ["peer"]
    assert status.detail["connection_count"] == 1


@pytest.mark.asyncio
async def test_state_transitions_publish_events() -> None:
    bus = EventBus()
    seen: list[MCPConnectionChangedEvent] = []
    bus.subscribe(MCPConnectionChangedEvent, seen.append)

    client = MCPClientRuntime(event_bus=bus)
    client.register_connection("peer", _FakeTransport())
    await client.connect("peer")
    await client.disconnect("peer")

    assert [e.state for e in seen] == ["connecting", "connected", "disconnected"]
    assert {e.server_id for e in seen} == {"peer"}


@pytest.mark.asyncio
async def test_runtime_works_without_an_event_bus() -> None:
    """Same optional-``event_bus`` pattern MemoryService established."""
    client = MCPClientRuntime(event_bus=None)
    client.register_connection("peer", _FakeTransport())
    assert await client.connect("peer") is True
