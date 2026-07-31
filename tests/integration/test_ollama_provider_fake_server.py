"""Smoke test for :class:`OllamaLLMProvider` against a fake HTTP server.

We do NOT depend on a running Ollama daemon — instead we stand up a tiny
aiohttp server that speaks the subset of the Ollama HTTP protocol used
by the ``ollama`` python client's ``chat(stream=True)`` and ``list()``.
"""

from __future__ import annotations

import json

import pytest
from aiohttp import web


@pytest.mark.asyncio
async def test_ollama_stream_against_fake_server(aiohttp_server) -> None:
    tokens = ["Hello", ", ", "world", "!"]

    async def handle_chat(request: web.Request) -> web.StreamResponse:
        # Ollama /api/chat streams NDJSON — one JSON object per line.
        body = await request.json()
        assert body["model"] == "test-model"
        assert body["stream"] is True

        resp = web.StreamResponse(
            status=200,
            headers={"Content-Type": "application/x-ndjson"},
        )
        await resp.prepare(request)
        for tok in tokens:
            chunk = {
                "model": "test-model",
                "message": {"role": "assistant", "content": tok},
                "done": False,
            }
            await resp.write((json.dumps(chunk) + "\n").encode("utf-8"))
        final = {
            "model": "test-model",
            "message": {"role": "assistant", "content": ""},
            "done": True,
        }
        await resp.write((json.dumps(final) + "\n").encode("utf-8"))
        await resp.write_eof()
        return resp

    async def handle_tags(_request: web.Request) -> web.Response:
        return web.json_response({"models": [{"name": "test-model"}]})

    app = web.Application()
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_get("/api/tags", handle_tags)
    server = await aiohttp_server(app)

    # Configure our provider to point at the fake server.
    from jarvis.core.config.settings import OllamaSettings
    from jarvis.core.types import ChatMessage
    from jarvis.infrastructure.llm.ollama_provider import OllamaLLMProvider

    settings = OllamaSettings(
        enabled=True,
        base_url=str(server.make_url("/")).rstrip("/"),
        model="test-model",
    )
    provider = OllamaLLMProvider(settings)

    # Health check.
    status = await provider.health()
    assert status.healthy is True

    # Stream.
    got: list[str] = []
    async for token in provider.stream([ChatMessage(role="user", content="ping")]):
        got.append(token)
    assert "".join(got) == "Hello, world!"

    # complete() aggregates.
    full = await provider.complete([ChatMessage(role="user", content="ping")])
    assert full == "Hello, world!"
