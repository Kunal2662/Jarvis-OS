"""Unit tests for the shared JSON-RPC stream channel -- Milestone 10.5
Task Group B. Exercised over an in-memory socket pair so the framing and
correlation logic is tested without a subprocess or a pipe."""

from __future__ import annotations

import asyncio
import json

import pytest

from jarvis.core.interfaces.mcp import MCPTransportError
from jarvis.core.mcp.transports.jsonrpc import JsonRpcStreamChannel


async def _channel_pair(
    responder,
) -> tuple[JsonRpcStreamChannel, asyncio.Server]:
    """A real channel talking to a real asyncio server on loopback."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            line = await reader.readline()
            if not line:
                return
            reply = responder(json.loads(line))
            if reply is not None:
                writer.write((json.dumps(reply) + "\n").encode())
                await writer.drain()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    channel = JsonRpcStreamChannel(reader, writer, request_timeout_seconds=2.0)
    channel.start()
    return channel, server


@pytest.mark.asyncio
async def test_request_returns_the_correlated_result() -> None:
    channel, server = await _channel_pair(
        lambda m: {"jsonrpc": "2.0", "id": m["id"], "result": {"echo": m["params"]["text"]}}
    )
    try:
        assert await channel.request("say", {"text": "hi"}) == {"echo": "hi"}
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_concurrent_requests_are_demultiplexed_by_id() -> None:
    """The whole reason a single read loop exists: several in-flight
    requests over one stream must not cross-deliver."""
    channel, server = await _channel_pair(
        lambda m: {"jsonrpc": "2.0", "id": m["id"], "result": {"n": m["params"]["n"]}}
    )
    try:
        results = await asyncio.gather(*(channel.request("n", {"n": i}) for i in range(20)))
        assert [r["n"] for r in results] == list(range(20))
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_peer_error_becomes_a_transport_error() -> None:
    channel, server = await _channel_pair(
        lambda m: {"jsonrpc": "2.0", "id": m["id"], "error": {"code": -1, "message": "nope"}}
    )
    try:
        with pytest.raises(MCPTransportError, match="nope"):
            await channel.request("boom")
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_non_dict_result_is_wrapped() -> None:
    channel, server = await _channel_pair(
        lambda m: {"jsonrpc": "2.0", "id": m["id"], "result": "plain"}
    )
    try:
        assert await channel.request("x") == {"result": "plain"}
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_unparseable_frame_is_discarded_without_killing_the_channel() -> None:
    """A peer logging to the wrong stream must not take the channel
    down -- the next well-formed response still arrives."""
    state = {"first": True}

    def responder(message):
        if state["first"]:
            state["first"] = False
            return None  # server writes nothing; we inject garbage below
        return {"jsonrpc": "2.0", "id": message["id"], "result": {"ok": True}}

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        line = await reader.readline()
        message = json.loads(line)
        writer.write(b"this is not json\n")
        writer.write(
            (
                json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": {"ok": True}}) + "\n"
            ).encode()
        )
        await writer.drain()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    channel = JsonRpcStreamChannel(reader, writer, request_timeout_seconds=2.0)
    channel.start()
    try:
        assert await channel.request("x") == {"ok": True}
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_timeout_raises_rather_than_hanging() -> None:
    channel, server = await _channel_pair(lambda m: None)
    channel._timeout = 0.15
    try:
        with pytest.raises(MCPTransportError, match="timed out"):
            await channel.request("silence")
    finally:
        await channel.close()
        server.close()


@pytest.mark.asyncio
async def test_close_fails_in_flight_requests_immediately() -> None:
    """Callers learn the channel died at once, which is what makes a
    prompt reconnect possible instead of waiting out every timeout."""
    channel, server = await _channel_pair(lambda m: None)
    try:
        pending = asyncio.ensure_future(channel.request("slow"))
        await asyncio.sleep(0.05)
        await channel.close("peer went away")

        with pytest.raises(MCPTransportError, match="peer went away"):
            await pending
    finally:
        server.close()


@pytest.mark.asyncio
async def test_request_after_close_is_refused() -> None:
    channel, server = await _channel_pair(lambda m: None)
    await channel.close()
    server.close()

    assert channel.is_closed is True
    with pytest.raises(MCPTransportError, match="closed"):
        await channel.request("x")


@pytest.mark.asyncio
async def test_close_is_idempotent() -> None:
    channel, server = await _channel_pair(lambda m: None)
    await channel.close()
    await channel.close()
    server.close()
