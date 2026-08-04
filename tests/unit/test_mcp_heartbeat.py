"""Unit tests for the MCP heartbeat monitor -- Milestone 10.5 Task
Group B, deliverables 1/2/7/8."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import MCPHeartbeatEvent
from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.heartbeat import MCPHeartbeatMonitor


class _Transport:
    transport_type = "in_process"

    def __init__(self, *, fail_ping: bool = False) -> None:
        self._connected = False
        self.fail_ping = fail_ping
        self.pings = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if method == "ping":
            self.pings += 1
            if self.fail_ping:
                raise MCPTransportError("peer is gone")
            return {"pong": True}
        if method == "initialize":
            return {"server_id": "peer", "agreed_version": "2025-06-18"}
        if method == "capabilities/list":
            return {"capabilities": []}
        return {}


async def _connected_client(**kwargs: Any) -> tuple[MCPClientRuntime, _Transport]:
    transport = _Transport(**kwargs)
    client = MCPClientRuntime()
    client.register_connection("peer", transport)
    await client.connect("peer")
    return client, transport


@pytest.mark.asyncio
async def test_beat_reports_a_live_peer_healthy() -> None:
    client, transport = await _connected_client()
    monitor = MCPHeartbeatMonitor(client)

    (result,) = await monitor.beat_once()

    assert result.healthy is True
    assert result.server_id == "peer"
    assert result.latency_ms >= 0.0
    assert transport.pings == 1


@pytest.mark.asyncio
async def test_beat_reports_a_dead_peer_unhealthy_without_raising() -> None:
    """A dead peer marks that connection unhealthy; recovery is the
    client runtime's existing reconnect, not a second manager here."""
    client, _ = await _connected_client(fail_ping=True)
    monitor = MCPHeartbeatMonitor(client)

    (result,) = await monitor.beat_once()

    assert result.healthy is False
    assert "peer is gone" in result.detail


@pytest.mark.asyncio
async def test_disconnected_peers_are_skipped() -> None:
    """Probing a peer that is not connected would generate a guaranteed
    failure that says nothing about liveness."""
    client, transport = await _connected_client()
    await client.disconnect("peer")
    monitor = MCPHeartbeatMonitor(client)

    assert await monitor.beat_once() == ()
    assert transport.pings == 0


@pytest.mark.asyncio
async def test_publishes_one_event_per_probe() -> None:
    bus = EventBus()
    seen: list[MCPHeartbeatEvent] = []
    bus.subscribe(MCPHeartbeatEvent, seen.append)

    client, _ = await _connected_client()
    monitor = MCPHeartbeatMonitor(client, event_bus=bus)
    await monitor.beat_once()

    assert len(seen) == 1
    assert seen[0].server_id == "peer"
    assert seen[0].healthy is True


@pytest.mark.asyncio
async def test_works_without_an_event_bus() -> None:
    client, _ = await _connected_client()
    monitor = MCPHeartbeatMonitor(client, event_bus=None)

    (result,) = await monitor.beat_once()
    assert result.healthy is True


@pytest.mark.asyncio
async def test_last_result_and_snapshot_expose_the_latest_state() -> None:
    client, _ = await _connected_client()
    monitor = MCPHeartbeatMonitor(client)
    await monitor.beat_once()

    last = monitor.last_result("peer")
    assert last is not None
    assert last.healthy is True

    (row,) = monitor.snapshot()
    assert row["server_id"] == "peer"
    assert row["healthy"] is True


@pytest.mark.asyncio
async def test_start_and_stop_are_idempotent() -> None:
    client, _ = await _connected_client()
    monitor = MCPHeartbeatMonitor(client, interval_seconds=1.0)

    await monitor.start()
    await monitor.start()
    assert monitor.is_running is True

    await monitor.stop()
    await monitor.stop()
    assert monitor.is_running is False


@pytest.mark.asyncio
async def test_stop_is_safe_before_start() -> None:
    client, _ = await _connected_client()
    await MCPHeartbeatMonitor(client).stop()


@pytest.mark.asyncio
async def test_the_loop_actually_probes_on_its_interval() -> None:
    client, transport = await _connected_client()
    monitor = MCPHeartbeatMonitor(client, interval_seconds=1.0)
    # The monitor clamps to >= 1s; drive the loop directly rather than
    # sleeping a real second in the test suite.
    monitor._interval = 0.05

    await monitor.start()
    await asyncio.sleep(0.2)
    await monitor.stop()

    assert transport.pings >= 2


@pytest.mark.asyncio
async def test_interval_is_clamped_to_a_sane_floor() -> None:
    client, _ = await _connected_client()
    monitor = MCPHeartbeatMonitor(client, interval_seconds=0.0)

    assert monitor._interval >= 1.0
