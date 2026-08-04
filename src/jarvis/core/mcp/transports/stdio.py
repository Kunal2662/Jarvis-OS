"""Stdio MCP transport -- Milestone 10.5 Task Group B, deliverable 1.

Spawns a peer process and speaks newline-delimited JSON-RPC over its
stdin/stdout, the framing the MCP specification defines for stdio. The
correlation logic lives in
:class:`~jarvis.core.mcp.transports.jsonrpc.JsonRpcStreamChannel`,
shared with the IPC transport -- this module owns only process
lifecycle.

Satisfies :class:`~jarvis.core.interfaces.mcp.IMCPTransport`
structurally, with no base class: the port is a Protocol, and every
other adapter in this codebase satisfies its port the same way.

**Reconnect is the client runtime's job, not this class's.** Task Group
A's ``MCPClientRuntime`` already owns bounded retry with backoff;
duplicating it per transport would be exactly the parallel connection
manager this task group's design rules forbid. A transport's
responsibility ends at "connect cleanly, fail loudly, tear down
completely" -- which is what makes the runtime's retry work at all.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.transports.jsonrpc import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    JsonRpcStreamChannel,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = get_logger("jarvis.core.mcp.transports.stdio")

DEFAULT_SHUTDOWN_GRACE_SECONDS = 5.0


class StdioTransport:
    """Runs an MCP peer as a child process."""

    transport_type = "stdio"

    def __init__(
        self,
        command: str,
        args: Sequence[str] = (),
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        shutdown_grace_seconds: float = DEFAULT_SHUTDOWN_GRACE_SECONDS,
    ) -> None:
        if not command:
            raise MCPTransportError("stdio transport requires a 'command'.")
        self._command = command
        self._args = list(args)
        self._cwd = cwd
        self._env = env
        self._request_timeout = request_timeout_seconds
        self._shutdown_grace = shutdown_grace_seconds
        self._process: asyncio.subprocess.Process | None = None
        self._channel: JsonRpcStreamChannel | None = None

    @property
    def is_connected(self) -> bool:
        return (
            self._process is not None
            and self._process.returncode is None
            and self._channel is not None
            and not self._channel.is_closed
        )

    @property
    def pid(self) -> int | None:
        return None if self._process is None else self._process.pid

    async def connect(self) -> None:
        """Idempotent -- reconnecting an already-live process is a no-op
        rather than orphaning the first one."""
        if self.is_connected:
            return
        await self._teardown("restarting")

        try:
            process = await asyncio.create_subprocess_exec(
                self._command,
                *self._args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
                env=self._env,
            )
        except (OSError, ValueError) as err:
            raise MCPTransportError(f"stdio: cannot start {self._command!r}: {err}") from err

        if process.stdin is None or process.stdout is None:
            with contextlib.suppress(Exception):
                process.kill()
            raise MCPTransportError(f"stdio: {self._command!r} exposed no stdin/stdout pipes.")

        self._process = process
        self._channel = JsonRpcStreamChannel(
            process.stdout,
            process.stdin,
            request_timeout_seconds=self._request_timeout,
            label=f"stdio[{self._command}]",
        )
        self._channel.start()
        _logger.info("MCP stdio transport connected: {} (pid {})", self._command, process.pid)

    async def disconnect(self) -> None:
        """Graceful shutdown: close stdin so a well-behaved peer exits on
        its own, wait briefly, then escalate to kill. Idempotent, and
        safe on a transport that never connected."""
        await self._teardown("disconnect")

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._channel is None or not self.is_connected:
            raise MCPTransportError(f"stdio: cannot call {method!r}: transport is not connected.")
        return await self._channel.request(method, params)

    async def _teardown(self, reason: str) -> None:
        if self._channel is not None:
            await self._channel.close(f"stdio: {reason}")
            self._channel = None

        process = self._process
        self._process = None
        if process is None or process.returncode is not None:
            return

        with contextlib.suppress(Exception):
            if process.stdin is not None and not process.stdin.is_closing():
                process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=self._shutdown_grace)
        except (TimeoutError, asyncio.CancelledError):
            _logger.warning(
                "MCP stdio peer {!r} did not exit within {}s; killing.",
                self._command,
                self._shutdown_grace,
            )
            with contextlib.suppress(Exception):
                process.kill()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await process.wait()
