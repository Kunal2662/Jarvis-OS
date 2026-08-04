"""WebSocket MCP transport -- Milestone 10.5 Task Group B, deliverable 2.

Speaks JSON-RPC over a persistent WebSocket to a remote MCP peer, using
the ``websockets`` library already in this project's dependency set (the
same one M8's frontend transport story assumes).

**Distinct from the Runtime WebSocket Hub.** ``core/lifecycle/
runtime_ws_hub.py`` is JARVIS *serving* its own event relay to its own
clients at ``/api/v1/ws``. This class is JARVIS *connecting outward* as
a client to somebody else's MCP server. They share a wire technology
and nothing else -- no code, no state, no lifecycle -- so this is not a
second event system.

Correlation is intentionally not shared with
:class:`~jarvis.core.mcp.transports.jsonrpc.JsonRpcStreamChannel`: that
class demultiplexes a byte stream it must frame itself, whereas a
WebSocket already delivers discrete messages. Reusing it here would
mean wrapping a message-oriented protocol in a stream abstraction just
to unwrap it again.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.transports.jsonrpc import DEFAULT_REQUEST_TIMEOUT_SECONDS

_logger = get_logger("jarvis.core.mcp.transports.websocket")

DEFAULT_OPEN_TIMEOUT_SECONDS = 10.0


class WebSocketTransport:
    """Connects outward to a remote MCP server over WebSocket."""

    transport_type = "websocket"

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        open_timeout_seconds: float = DEFAULT_OPEN_TIMEOUT_SECONDS,
    ) -> None:
        if not url:
            raise MCPTransportError("websocket transport requires a 'url'.")
        self._url = url
        self._headers = headers or {}
        self._request_timeout = request_timeout_seconds
        self._open_timeout = open_timeout_seconds
        self._connection: Any = None
        self._next_id = 0
        self._pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self._read_task: asyncio.Task[None] | None = None

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and self._read_task is not None

    async def connect(self) -> None:
        if self.is_connected:
            return
        await self._teardown("reconnecting")

        from websockets.asyncio.client import connect as ws_connect

        try:
            self._connection = await asyncio.wait_for(
                ws_connect(self._url, additional_headers=self._headers),
                timeout=self._open_timeout,
            )
        except (TimeoutError, OSError, Exception) as err:
            self._connection = None
            raise MCPTransportError(f"websocket: cannot connect to {self._url}: {err}") from err

        self._read_task = asyncio.create_task(self._read_loop())
        _logger.info("MCP websocket transport connected: {}", self._url)

    async def disconnect(self) -> None:
        await self._teardown("disconnect")

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.is_connected or self._connection is None:
            raise MCPTransportError(
                f"websocket: cannot call {method!r}: transport is not connected."
            )

        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future

        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        try:
            await self._connection.send(json.dumps(payload))
        except Exception as err:
            self._pending.pop(request_id, None)
            raise MCPTransportError(f"websocket: send failed: {err}") from err

        try:
            return await asyncio.wait_for(future, timeout=self._request_timeout)
        except TimeoutError as err:
            self._pending.pop(request_id, None)
            raise MCPTransportError(
                f"websocket: {method!r} timed out after {self._request_timeout}s."
            ) from err

    async def _read_loop(self) -> None:
        connection = self._connection
        if connection is None:
            return
        try:
            async for raw in connection:
                self._dispatch(raw)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self._fail_pending(f"websocket: connection lost: {err}")
        else:
            self._fail_pending("websocket: peer closed the connection.")

    def _dispatch(self, raw: str | bytes) -> None:
        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            message = json.loads(text)
        except (ValueError, UnicodeDecodeError) as err:
            _logger.warning("websocket: discarding unparseable frame: {}", err)
            return
        if not isinstance(message, dict):
            return

        raw_id = message.get("id")
        if not isinstance(raw_id, int):
            return
        future = self._pending.pop(raw_id, None)
        if future is None or future.done():
            return

        error = message.get("error")
        if error is not None:
            detail = error.get("message", error) if isinstance(error, dict) else error
            future.set_exception(MCPTransportError(f"websocket: peer error: {detail}"))
            return
        result = message.get("result")
        future.set_result(result if isinstance(result, dict) else {"result": result})

    def _fail_pending(self, reason: str) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(MCPTransportError(reason))
        self._pending.clear()

    async def _teardown(self, reason: str) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._read_task
            self._read_task = None

        self._fail_pending(f"websocket: {reason}")

        if self._connection is not None:
            with contextlib.suppress(Exception):
                await self._connection.close()
            self._connection = None
