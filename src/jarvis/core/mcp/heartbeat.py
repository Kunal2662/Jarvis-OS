"""MCP heartbeat -- Milestone 10.5 Task Group B, deliverables 1/2/7/8.

Liveness checking for every connected MCP peer, as a *composed*
collaborator rather than a method on the transport port.

**Why not a ``ping()`` on ``IMCPTransport``.** Adding one would have
forced every transport -- including Task Group A's shipped
``InProcessTransport`` -- to implement it, for a concern that is
identical across all of them: send ``ping``, measure the round trip,
decide if the peer is alive. Heartbeat rides the ``request`` primitive
each transport already provides, so a transport added in a later
milestone gets heartbeat for free with no extra code.

**One periodic loop, not one per connection.** A single monitor polls
every registered connection, the same way M9's ``HealthMonitor`` polls
every service rather than each service spawning its own timer. Failures
are reported, never raised: a dead peer marks that connection
unhealthy, and the client runtime's existing reconnect handles recovery
-- there is no second connection manager here.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from jarvis.core.events.events import MCPHeartbeatEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.mcp.client import MCPClientRuntime

_logger = get_logger("jarvis.core.mcp.heartbeat")

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30.0

#: The JSON-RPC method a peer answers to prove liveness. Registered as a
#: built-in on ``MCPServerRuntime`` through Task Group A's own
#: ``register_method`` extension seam -- not by editing its dispatch.
HEARTBEAT_METHOD = "ping"


@dataclass(frozen=True, slots=True)
class HeartbeatResult:
    server_id: str
    healthy: bool
    latency_ms: float = 0.0
    detail: str = ""


class MCPHeartbeatMonitor:
    """Periodically proves every connected MCP peer is still answering."""

    def __init__(
        self,
        client_runtime: MCPClientRuntime,
        *,
        event_bus: EventBus | None = None,
        interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        self._client = client_runtime
        self._event_bus = event_bus
        self._interval = max(1.0, interval_seconds)
        self._task: asyncio.Task[None] | None = None
        self._last: dict[str, HeartbeatResult] = {}

    # ------------------------------------------------------------------
    # Probing
    # ------------------------------------------------------------------
    async def beat_once(self) -> tuple[HeartbeatResult, ...]:
        """One pass over every connected peer. Never raises."""
        from jarvis.core.mcp.client import MCPConnectionState

        results: list[HeartbeatResult] = []
        for server_id in self._client.server_ids:
            connection = self._client.get(server_id)
            if connection is None or connection.state is not MCPConnectionState.CONNECTED:
                continue
            results.append(await self._beat(server_id, connection))
        return tuple(results)

    async def _beat(self, server_id: str, connection: object) -> HeartbeatResult:
        started = time.perf_counter()
        try:
            transport = connection.transport  # type: ignore[attr-defined]
            await transport.request(HEARTBEAT_METHOD, {})
        except Exception as err:
            result = HeartbeatResult(server_id=server_id, healthy=False, detail=str(err))
            _logger.warning("MCP heartbeat failed for {!r}: {}", server_id, err)
        else:
            result = HeartbeatResult(
                server_id=server_id,
                healthy=True,
                latency_ms=(time.perf_counter() - started) * 1000,
            )

        self._last[server_id] = result
        await self._publish(result)
        return result

    async def _publish(self, result: HeartbeatResult) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPHeartbeatEvent(
                server_id=result.server_id,
                healthy=result.healthy,
                latency_ms=round(result.latency_ms, 3),
                detail=result.detail,
            )
        )

    # ------------------------------------------------------------------
    # Lifecycle -- mirrors HealthMonitor's own start/stop exactly
    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    @property
    def is_running(self) -> bool:
        return self._task is not None

    async def _loop(self) -> None:
        while True:
            try:
                await self.beat_once()
            except Exception:
                _logger.exception("MCP heartbeat tick failed.")
            await asyncio.sleep(self._interval)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def last_result(self, server_id: str) -> HeartbeatResult | None:
        return self._last.get(server_id)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "server_id": r.server_id,
                "healthy": r.healthy,
                "latency_ms": round(r.latency_ms, 3),
                "detail": r.detail,
            }
            for r in self._last.values()
        )
