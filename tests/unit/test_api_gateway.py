"""API Gateway tests -- Milestone 11 Task Group E.

Against a real ``aiohttp`` server speaking a vendor's wire protocol,
matching ``test_ollama_provider_fake_server.py``'s established pattern.
Real HTTP throughout: the gateway's whole job is retry, caching and
error mapping over ``httpx``, and mocking ``httpx`` away would test the
mock.

The retry tests are the ones that matter most. A retried ``GET`` costs a
round trip; a retried ``POST /messages/send`` sends the email twice.
"""

from __future__ import annotations

import pytest
from aiohttp import web

from jarvis.core.integrations.gateway import (
    ApiGateway,
    GatewayError,
    GatewayRequest,
)


@pytest.fixture
async def gateway():
    api = ApiGateway(max_attempts=3, backoff_seconds=0.0, cache_ttl_seconds=30.0)
    await api.start()
    try:
        yield api
    finally:
        await api.stop()


def _request(url: str, **overrides) -> GatewayRequest:
    defaults = {
        "integration_id": "acme",
        "operation": "messages.list",
        "method": "GET",
        "url": url,
        "account_key": "acme:me",
    }
    defaults.update(overrides)
    return GatewayRequest(**defaults)  # type: ignore[arg-type]


# --- happy path -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_successful_call_returns_parsed_json(aiohttp_server, gateway) -> None:
    async def handler(request: web.Request) -> web.Response:
        assert request.query.get("q") == "hello"
        assert request.headers.get("Authorization") == "Bearer t0ken"
        return web.json_response({"messages": [{"id": "m1"}]})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)

    result = await gateway.send(
        _request(
            str(server.make_url("/v1/messages")),
            query={"q": "hello"},
            headers={"Authorization": "Bearer t0ken"},
        )
    )

    assert result.ok
    assert result.status_code == 200
    assert result.data == {"messages": [{"id": "m1"}]}
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_a_post_sends_its_body(aiohttp_server, gateway) -> None:
    seen: list[dict] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(await request.json())
        return web.json_response({"id": "sent-1"}, status=200)

    app = web.Application()
    app.router.add_post("/v1/send", handler)
    server = await aiohttp_server(app)

    await gateway.send(
        _request(
            str(server.make_url("/v1/send")),
            method="POST",
            operation="messages.send",
            body={"raw": "encoded"},
        )
    )

    assert seen == [{"raw": "encoded"}]


@pytest.mark.asyncio
async def test_an_empty_204_is_a_success_not_a_parse_failure(aiohttp_server, gateway) -> None:
    async def handler(_request: web.Request) -> web.Response:
        return web.Response(status=204)

    app = web.Application()
    app.router.add_delete("/v1/things/1", handler)
    server = await aiohttp_server(app)

    result = await gateway.send(
        _request(str(server.make_url("/v1/things/1")), method="DELETE", operation="things.delete")
    )

    assert result.ok
    assert result.data is None


# --- retry --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_transient_500_is_retried(aiohttp_server, gateway) -> None:
    attempts = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        attempts["n"] += 1
        if attempts["n"] < 3:
            return web.json_response({"error": "flaky"}, status=503)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)

    result = await gateway.send(_request(str(server.make_url("/v1/messages"))))

    assert result.ok
    assert result.attempts == 3
    assert gateway.stats()["retries"] == 2


@pytest.mark.asyncio
async def test_a_mutating_call_is_never_retried(aiohttp_server, gateway) -> None:
    """The property this whole design exists for: a retried send sends
    twice, and no amount of backoff makes that acceptable."""
    attempts = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        attempts["n"] += 1
        return web.json_response({"error": "server on fire"}, status=503)

    app = web.Application()
    app.router.add_post("/v1/send", handler)
    server = await aiohttp_server(app)

    with pytest.raises(GatewayError):
        await gateway.send(
            _request(str(server.make_url("/v1/send")), method="POST", operation="messages.send")
        )

    assert attempts["n"] == 1


@pytest.mark.asyncio
async def test_a_4xx_is_not_retried(aiohttp_server, gateway) -> None:
    """A 403 is the caller's problem; retrying it just spends quota."""
    attempts = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        attempts["n"] += 1
        return web.json_response({"error": {"message": "insufficient scope"}}, status=403)

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)

    with pytest.raises(GatewayError) as caught:
        await gateway.send(_request(str(server.make_url("/v1/messages"))))

    assert attempts["n"] == 1
    assert caught.value.status_code == 403
    assert "insufficient scope" in str(caught.value)


@pytest.mark.asyncio
async def test_a_429_is_retried_and_honours_retry_after(aiohttp_server, gateway) -> None:
    attempts = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return web.json_response(
                {"error": "slow down"}, status=429, headers={"Retry-After": "0"}
            )
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)

    result = await gateway.send(_request(str(server.make_url("/v1/messages"))))

    assert result.ok
    assert attempts["n"] == 2


@pytest.mark.asyncio
async def test_exhausted_retries_raise_with_the_vendor_reason(aiohttp_server, gateway) -> None:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response({"error": {"message": "still broken"}}, status=500)

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)

    with pytest.raises(GatewayError, match="still broken"):
        await gateway.send(_request(str(server.make_url("/v1/messages"))))

    assert gateway.stats()["failures"] == 1


@pytest.mark.asyncio
async def test_an_unreachable_host_raises_rather_than_hanging(gateway) -> None:
    with pytest.raises(GatewayError):
        # Port 9 is discard; nothing listens on it.
        await gateway.send(_request("http://127.0.0.1:9/v1/messages"))


# --- caching --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_repeated_get_is_served_from_cache(aiohttp_server, gateway) -> None:
    hits = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        hits["n"] += 1
        return web.json_response({"n": hits["n"]})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)
    request = _request(str(server.make_url("/v1/messages")))

    first = await gateway.send(request)
    second = await gateway.send(request)

    assert hits["n"] == 1
    assert second.from_cache is True
    assert second.data == first.data


@pytest.mark.asyncio
async def test_another_account_never_reads_the_first_ones_cache(aiohttp_server, gateway) -> None:
    """The cache key leads with the account precisely so one user's
    inbox listing can never be served to another."""
    hits = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        hits["n"] += 1
        return web.json_response({"n": hits["n"]})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)
    url = str(server.make_url("/v1/messages"))

    await gateway.send(_request(url, account_key="acme:alice"))
    result = await gateway.send(_request(url, account_key="acme:bob"))

    assert hits["n"] == 2
    assert result.from_cache is False


@pytest.mark.asyncio
async def test_a_mutating_call_drops_that_accounts_cache(aiohttp_server, gateway) -> None:
    """Someone who just sent a message and then lists messages must not
    be told it is not there."""
    hits = {"n": 0}

    async def listing(_request: web.Request) -> web.Response:
        hits["n"] += 1
        return web.json_response({"n": hits["n"]})

    async def send(_request: web.Request) -> web.Response:
        return web.json_response({"id": "sent"})

    app = web.Application()
    app.router.add_get("/v1/messages", listing)
    app.router.add_post("/v1/send", send)
    server = await aiohttp_server(app)

    listing_request = _request(str(server.make_url("/v1/messages")))
    await gateway.send(listing_request)
    await gateway.send(
        _request(str(server.make_url("/v1/send")), method="POST", operation="messages.send")
    )
    after = await gateway.send(listing_request)

    assert after.from_cache is False
    assert hits["n"] == 2


@pytest.mark.asyncio
async def test_a_mutating_call_is_never_cached(aiohttp_server, gateway) -> None:
    calls = {"n": 0}

    async def handler(_request: web.Request) -> web.Response:
        calls["n"] += 1
        return web.json_response({"id": calls["n"]})

    app = web.Application()
    app.router.add_post("/v1/send", handler)
    server = await aiohttp_server(app)
    request = _request(str(server.make_url("/v1/send")), method="POST", operation="messages.send")

    await gateway.send(request)
    await gateway.send(request)

    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_invalidate_clears_one_accounts_entries(aiohttp_server, gateway) -> None:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)
    url = str(server.make_url("/v1/messages"))

    await gateway.send(_request(url, account_key="acme:alice"))
    await gateway.send(_request(url, account_key="acme:bob"))

    assert gateway.invalidate("acme:alice") == 1
    assert gateway.stats()["cache_entries"] == 1


# --- lifecycle and audit --------------------------------------------------------


@pytest.mark.asyncio
async def test_calling_a_closed_gateway_is_refused() -> None:
    api = ApiGateway()
    with pytest.raises(GatewayError, match="not open"):
        await api.send(_request("https://api.acme.test/v1/messages"))


@pytest.mark.asyncio
async def test_start_is_idempotent(gateway) -> None:
    await gateway.start()
    await gateway.start()
    assert gateway.is_open


@pytest.mark.asyncio
async def test_stop_is_safe_on_a_gateway_that_never_started() -> None:
    await ApiGateway().stop()


def test_the_audit_payload_carries_no_headers_and_no_body() -> None:
    """A request body can be the text of an email; a header can be a
    token. The audit trail records neither."""
    audit = _request(
        "https://api.acme.test/v1/send",
        method="POST",
        body={"raw": "dear alice, the password is hunter2"},
        headers={"Authorization": "Bearer super-secret"},
        query={"q": "private"},
    ).audit()

    rendered = str(audit)
    assert "hunter2" not in rendered
    assert "super-secret" not in rendered
    assert "private" not in rendered  # only the *keys* travel
    assert audit["query_keys"] == ["q"]
    assert audit["has_body"] is True


@pytest.mark.asyncio
async def test_stats_count_calls_failures_and_cache_hits(aiohttp_server, gateway) -> None:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/v1/messages", handler)
    server = await aiohttp_server(app)
    request = _request(str(server.make_url("/v1/messages")))

    await gateway.send(request)
    await gateway.send(request)

    stats = gateway.stats()
    assert stats["calls"] == 1
    assert stats["cache_hits"] == 1
    assert stats["failures"] == 0
    assert stats["open"] is True
