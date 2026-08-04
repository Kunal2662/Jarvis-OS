"""Newline-delimited JSON-RPC over an asyncio stream pair -- Milestone
10.5 Task Group B.

The framing and request/response correlation both ``stdio`` and ``ipc``
need, written once. Neither transport reimplements it: they differ only
in *how* they obtain the ``(StreamReader, StreamWriter)`` pair (a
subprocess' pipes versus a local socket/named pipe), which is exactly
the kind of difference composition handles and inheritance would
obscure.

MCP's stdio framing is one JSON object per line -- no ``Content-Length``
header block. A single background read loop demultiplexes responses to
the futures waiting on their request id, so concurrent in-flight
requests over one channel are safe.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.logging.logger import get_logger

_logger = get_logger("jarvis.core.mcp.transports.jsonrpc")

DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0

#: Guards against a peer streaming an unbounded line into memory. Well
#: past any realistic capability list; a peer exceeding it is
#: malfunctioning or hostile, and either way the channel should fail
#: loudly rather than exhaust the process.
MAX_LINE_BYTES = 8 * 1024 * 1024


class JsonRpcStreamChannel:
    """Correlates JSON-RPC requests and responses over one stream pair."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        label: str = "jsonrpc",
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._timeout = request_timeout_seconds
        self._label = label
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._closed = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Begins the demultiplexing read loop. Idempotent."""
        if self._read_task is None:
            self._read_task = asyncio.create_task(self._read_loop())

    async def close(self, reason: str = "channel closed") -> None:
        """Idempotent. Every in-flight request fails with *reason* rather
        than hanging until its own timeout -- a caller learns the channel
        died immediately, which is what makes prompt reconnect possible."""
        if self._closed:
            return
        self._closed = True

        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None

        self._fail_pending(reason)

        with contextlib.suppress(Exception):
            self._writer.close()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await self._writer.wait_closed()

    @property
    def is_closed(self) -> bool:
        return self._closed

    # ------------------------------------------------------------------
    # Request / response
    # ------------------------------------------------------------------
    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._closed:
            raise MCPTransportError(f"{self._label}: channel is closed.")

        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        try:
            self._writer.write(json.dumps(payload).encode("utf-8") + b"\n")
            await self._writer.drain()
        except Exception as err:
            self._pending.pop(request_id, None)
            raise MCPTransportError(f"{self._label}: write failed: {err}") from err

        try:
            return await asyncio.wait_for(future, timeout=self._timeout)
        except TimeoutError as err:
            self._pending.pop(request_id, None)
            raise MCPTransportError(
                f"{self._label}: {method!r} timed out after {self._timeout}s."
            ) from err

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    async def _read_loop(self) -> None:
        try:
            while True:
                line = await self._reader.readline()
                if not line:
                    self._fail_pending(f"{self._label}: peer closed the stream.")
                    return
                if len(line) > MAX_LINE_BYTES:
                    self._fail_pending(f"{self._label}: peer sent an oversized frame.")
                    return
                self._dispatch(line)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._fail_pending(f"{self._label}: read loop failed: {err}")

    def _dispatch(self, line: bytes) -> None:
        try:
            message = json.loads(line.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as err:
            # One malformed frame must not kill the channel -- the peer
            # may simply have logged to the wrong stream.
            _logger.warning("{}: discarding unparseable frame: {}", self._label, err)
            return
        if not isinstance(message, dict):
            return

        raw_id = message.get("id")
        if not isinstance(raw_id, int):
            return  # a notification, or a response we never asked for
        future = self._pending.pop(raw_id, None)
        if future is None or future.done():
            return

        error = message.get("error")
        if error is not None:
            detail = error.get("message", error) if isinstance(error, dict) else error
            future.set_exception(MCPTransportError(f"{self._label}: peer error: {detail}"))
            return
        result = message.get("result")
        future.set_result(result if isinstance(result, dict) else {"result": result})

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(MCPTransportError(reason))
        self._pending.clear()
