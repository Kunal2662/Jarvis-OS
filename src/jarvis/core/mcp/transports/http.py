"""HTTP MCP transport -- Milestone 10.5 Task Group B, deliverable 3.

Stateless JSON-RPC over HTTP POST: one request, one response, no
persistent channel. Uses ``httpx``, already this project's HTTP client
everywhere else.

**"Connected" means something different here, honestly.** There is no
socket to hold open, so :meth:`connect` opens a pooled
``httpx.AsyncClient`` and performs a real reachability check rather than
optimistically reporting success -- otherwise every stateless transport
would claim to be connected to an unreachable host, and the client
runtime's retry logic would have nothing to react to. :meth:`disconnect`
closes the pool.

Capability discovery, negotiation and health all ride the same
``request`` primitive the other transports expose, so nothing above this
layer branches on statelessness.
"""

from __future__ import annotations

import contextlib
from typing import Any

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.transports.jsonrpc import DEFAULT_REQUEST_TIMEOUT_SECONDS

_logger = get_logger("jarvis.core.mcp.transports.http")


class HttpTransport:
    """Stateless MCP peer access over HTTP POST."""

    transport_type = "http"

    def __init__(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
        verify: bool = True,
    ) -> None:
        if not url:
            raise MCPTransportError("http transport requires a 'url'.")
        self._url = url
        self._headers = headers or {}
        self._timeout = request_timeout_seconds
        self._verify = verify
        self._client: Any = None
        self._next_id = 0

    @property
    def url(self) -> str:
        return self._url

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    async def connect(self) -> None:
        """Opens the connection pool and verifies the peer answers.

        The probe deliberately does **not** go through :meth:`request`.
        That method converts every ``httpx`` failure into
        ``MCPTransportError``, which would make "host unreachable"
        indistinguishable from "peer answered with a JSON-RPC error" --
        and swallowing the latter would mean an unreachable endpoint
        silently reported itself connected. Here only a genuine
        transport failure (DNS, refused, TLS, timeout) fails the
        connect; any HTTP response at all, including a 4xx/5xx or a
        JSON-RPC error body, proves reachability, which is the only
        thing a stateless transport's ``connect`` can honestly assert.
        """
        if self.is_connected:
            return

        import httpx

        client = httpx.AsyncClient(
            timeout=self._timeout,
            headers={"Content-Type": "application/json", **self._headers},
            verify=self._verify,
        )
        probe = {"jsonrpc": "2.0", "id": 0, "method": "ping", "params": {}}
        try:
            await client.post(self._url, json=probe)
        except httpx.HTTPError as err:
            with contextlib.suppress(Exception):
                await client.aclose()
            raise MCPTransportError(f"http: cannot reach {self._url}: {err}") from err

        self._client = client
        _logger.info("MCP http transport connected: {}", self._url)

    async def disconnect(self) -> None:
        await self._close_client()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._client is None:
            raise MCPTransportError(f"http: cannot call {method!r}: transport is not connected.")

        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id,
            "method": method,
            "params": params or {},
        }

        import httpx

        try:
            response = await self._client.post(self._url, json=payload)
            response.raise_for_status()
            message = response.json()
        except httpx.HTTPError as err:
            raise MCPTransportError(f"http: {method!r} failed: {err}") from err
        except ValueError as err:
            raise MCPTransportError(f"http: {method!r} returned invalid JSON: {err}") from err

        if not isinstance(message, dict):
            raise MCPTransportError(f"http: {method!r} returned a non-object response.")

        error = message.get("error")
        if error is not None:
            detail = error.get("message", error) if isinstance(error, dict) else error
            raise MCPTransportError(f"http: peer error on {method!r}: {detail}")

        result = message.get("result")
        return result if isinstance(result, dict) else {"result": result}

    async def _close_client(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()
