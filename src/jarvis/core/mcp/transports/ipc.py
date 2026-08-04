"""Local IPC MCP transport -- Milestone 10.5 Task Group B, deliverable 4.

Talks to an MCP peer on the same machine over the OS's own local
channel: a **named pipe** on Windows, a **Unix domain socket**
elsewhere. Both yield an ``(asyncio.StreamReader, StreamWriter)`` pair,
so the JSON-RPC framing and correlation are the identical
:class:`~jarvis.core.mcp.transports.jsonrpc.JsonRpcStreamChannel` the
stdio transport uses -- the platform difference is confined to the six
lines that obtain the streams.

**Why not loopback TCP.** A TCP socket on ``127.0.0.1`` would have been
one implementation for every platform, but it is not actually local
IPC: it occupies a port, is reachable by any process that can bind a
client socket, and carries none of the OS-level access control a named
pipe or a filesystem-permissioned socket does. Local-first and
security-by-design both point the same way here, so the transport pays
one branch to get the real primitive.

Contains no provider-specific logic, per this task group's own scope
rule -- it is a channel, and it does not know or care what speaks over it.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.transports.jsonrpc import (
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    JsonRpcStreamChannel,
)

_logger = get_logger("jarvis.core.mcp.transports.ipc")


def default_endpoint_prefix() -> str:
    """The platform's conventional local-endpoint namespace."""
    return r"\\.\pipe" if sys.platform == "win32" else "/tmp"


class IpcTransport:
    """Connects to a local MCP peer over a named pipe or Unix socket."""

    transport_type = "ipc"

    def __init__(
        self,
        endpoint: str,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        if not endpoint:
            raise MCPTransportError("ipc transport requires an 'endpoint'.")
        self._endpoint = endpoint
        self._request_timeout = request_timeout_seconds
        self._channel: JsonRpcStreamChannel | None = None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    @property
    def is_connected(self) -> bool:
        return self._channel is not None and not self._channel.is_closed

    async def connect(self) -> None:
        if self.is_connected:
            return
        await self.disconnect()

        try:
            reader, writer = await self._open_streams()
        except (OSError, NotImplementedError, ValueError) as err:
            raise MCPTransportError(f"ipc: cannot connect to {self._endpoint!r}: {err}") from err

        self._channel = JsonRpcStreamChannel(
            reader,
            writer,
            request_timeout_seconds=self._request_timeout,
            label=f"ipc[{self._endpoint}]",
        )
        self._channel.start()
        _logger.info("MCP ipc transport connected: {}", self._endpoint)

    async def disconnect(self) -> None:
        if self._channel is not None:
            await self._channel.close("ipc: disconnect")
            self._channel = None

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._channel is None or not self.is_connected:
            raise MCPTransportError(f"ipc: cannot call {method!r}: transport is not connected.")
        return await self._channel.request(method, params)

    async def _open_streams(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """The one place the platform difference lives."""
        if sys.platform == "win32":
            return await _open_windows_pipe(self._endpoint)
        return await asyncio.open_unix_connection(self._endpoint)


async def _open_windows_pipe(
    endpoint: str,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Named-pipe client over the Proactor loop.

    ``asyncio`` exposes no ``open_pipe_connection`` helper the way it
    does ``open_unix_connection``, so the reader/writer pair is assembled
    from the loop's own ``create_pipe_connection`` primitive -- the same
    three steps ``open_unix_connection`` performs internally.
    """
    loop = asyncio.get_running_loop()
    create_pipe_connection = getattr(loop, "create_pipe_connection", None)
    if create_pipe_connection is None:
        raise MCPTransportError(
            "ipc: named pipes need the Proactor event loop; this loop does not support them."
        )

    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await create_pipe_connection(lambda: protocol, endpoint)
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer
