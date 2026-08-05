"""RestIntegrationProvider tests -- Milestone 11 Task Group E.

The lifecycle, permission and health tests the task brief requires, on
the class that makes "every connector is an MCP provider" literally
true. Real ``MCPAuthManager``, real ``CredentialStore``, real
``PermissionModel``, real ``ApiGateway`` against a real fake vendor
server -- only the vendor is fake, because only the vendor is
unavailable.

The permission tests are the load-bearing ones. Two independent gates
guard every call, and conflating them would be a security bug: the
operator's grant in the shared ``PermissionModel``, and the vendor
scopes the token actually carries.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from aiohttp import web

from jarvis.core.events.event_bus import EventBus
from jarvis.core.integrations.gateway import ApiGateway, GatewayError
from jarvis.core.integrations.models import (
    AuthSpec,
    IntegrationError,
    IntegrationSpec,
    OperationSpec,
)
from jarvis.core.integrations.provider import RestIntegrationProvider
from jarvis.core.mcp.auth.credentials import AuthMethod, Credential
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.server import principal_for
from jarvis.core.plugins.permissions import PermissionModel


def _spec(base_url: str) -> IntegrationSpec:
    return IntegrationSpec(
        integration_id="acme_mail",
        name="Acme Mail",
        vendor="acme",
        base_url=base_url,
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
        ),
        search_operation="messages.search",
        operations=(
            OperationSpec(
                name="messages.list",
                method="GET",
                path="/v1/users/{user_id}/messages",
                description="List messages.",
                permissions=("network",),
                scopes=("vendor.read",),
                query=("q", "maxResults"),
            ),
            OperationSpec(
                name="messages.search",
                method="GET",
                path="/v1/users/{user_id}/messages",
                description="Search messages.",
                category="search",
                permissions=("network",),
                scopes=("vendor.read",),
                query=("q", "maxResults"),
                required=("q",),
            ),
            OperationSpec(
                name="messages.send",
                method="POST",
                path="/v1/users/{user_id}/messages/send",
                description="Send a message.",
                category="write",
                permissions=("network",),
                scopes=("vendor.send",),
                body=("raw",),
                required=("raw",),
            ),
            OperationSpec(
                name="files.get",
                method="GET",
                path="/v1/files/{file_id}",
                description="Download a file.",
                category="download",
                permissions=("network", "filesystem"),
                scopes=("vendor.read",),
            ),
        ),
    )


class _Env:
    def __init__(self, tmp_path: Path, base_url: str) -> None:
        self.bus = EventBus()
        self.permissions = PermissionModel(self.bus, store_path=tmp_path / "permissions.json")
        self.store = CredentialStore(tmp_path / "credentials.json", secret_key="")
        self.auth = MCPAuthManager(
            self.store, build_default_strategy_registry(), self.permissions, event_bus=self.bus
        )
        self.gateway = ApiGateway(max_attempts=2, backoff_seconds=0.0)
        self.spec = _spec(base_url)
        self.provider = RestIntegrationProvider(
            self.spec, gateway=self.gateway, auth_manager=self.auth, account_id="me"
        )

    async def grant(self, *scopes: str) -> None:
        principal = principal_for(self.spec.integration_id)
        self.permissions.declare(principal, list(scopes))
        for scope in scopes:
            await self.permissions.grant(principal, scope)

    def store_credential(self, *, scopes: tuple[str, ...] = ("vendor.read",), **kwargs) -> None:
        defaults = {
            "provider_id": self.spec.integration_id,
            "method": AuthMethod.OAUTH2,
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "scopes": scopes,
        }
        defaults.update(kwargs)
        self.store.put(Credential(**defaults), persist=False)  # type: ignore[arg-type]


@pytest.fixture
async def vendor(aiohttp_server):
    """A fake Acme Mail. Records what it was asked for."""
    seen: list[web.Request] = []

    async def listing(request: web.Request) -> web.Response:
        seen.append(request)
        return web.json_response({"messages": [{"id": "m1", "subject": "hello"}]})

    async def send(request: web.Request) -> web.Response:
        seen.append(request)
        return web.json_response({"id": "sent-1"})

    app = web.Application()
    app.router.add_get("/v1/users/{user_id}/messages", listing)
    app.router.add_post("/v1/users/{user_id}/messages/send", send)
    server = await aiohttp_server(app)
    server.seen = seen  # type: ignore[attr-defined]
    return server


@pytest.fixture
async def env(tmp_path: Path, vendor):
    environment = _Env(tmp_path, str(vendor.make_url("")).rstrip("/"))
    try:
        yield environment
    finally:
        await environment.gateway.stop()


# --- lifecycle ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_registers_every_operation_as_a_capability(env) -> None:
    """The same MCPCapabilityRegistry an MCP peer's capabilities go
    into -- a third owner, which its docstring already allowed for."""
    await env.provider.initialize()

    assert set(env.provider.capabilities.names) == {
        "acme_mail.messages.list",
        "acme_mail.messages.search",
        "acme_mail.messages.send",
        "acme_mail.files.get",
    }
    capability = env.provider.capabilities.get("acme_mail.messages.send")
    assert capability.metadata["mutating"] is True


@pytest.mark.asyncio
async def test_initialize_touches_no_network(env, vendor) -> None:
    """The Protocol says initialization validates configuration and that
    connect owns I/O."""
    await env.provider.initialize()
    assert vendor.seen == []


@pytest.mark.asyncio
async def test_initialize_is_idempotent(env) -> None:
    await env.provider.initialize()
    await env.provider.initialize()
    assert len(env.provider.capabilities) == 4


@pytest.mark.asyncio
async def test_starting_without_a_credential_is_refused(env) -> None:
    with pytest.raises(IntegrationError, match="no usable credential"):
        await env.provider.start()


@pytest.mark.asyncio
async def test_start_with_a_credential_connects_without_calling_the_vendor(env, vendor) -> None:
    """An integration that spent an API call every time JARVIS started
    would burn quota proving what the credential already says."""
    env.store_credential()

    await env.provider.start()

    assert (await env.provider.health()).healthy is True
    assert vendor.seen == []


@pytest.mark.asyncio
async def test_stop_does_not_close_the_shared_gateway(env) -> None:
    """The pool is shared -- one integration disconnecting must not cut
    off every other one."""
    env.store_credential()
    await env.provider.start()

    await env.provider.stop()

    assert env.gateway.is_open is True


@pytest.mark.asyncio
async def test_suspend_then_resume(env) -> None:
    env.store_credential()
    await env.provider.start()

    await env.provider.suspend()
    assert (await env.provider.health()).healthy is False

    await env.provider.resume()
    assert (await env.provider.health()).healthy is True


@pytest.mark.asyncio
async def test_shutdown_clears_capabilities(env) -> None:
    env.store_credential()
    await env.provider.start()

    await env.provider.shutdown()

    assert len(env.provider.capabilities) == 0


# --- permission gates -----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_call_needs_the_jarvis_grant(env) -> None:
    """Gate one: the operator has not allowed this provider to use the
    network, so nothing leaves."""
    env.store_credential()
    await env.provider.start()

    with pytest.raises(IntegrationError, match="permission"):
        await env.provider.invoke("messages.list", {"user_id": "me"})


@pytest.mark.asyncio
async def test_a_call_needs_the_vendor_scope(env) -> None:
    """Gate two: the operator granted it, but the token does not carry
    the scope the endpoint needs. No amount of local granting can
    conjure one."""
    await env.grant("network")
    env.store_credential(scopes=("vendor.read",))
    await env.provider.start()

    with pytest.raises(IntegrationError, match="provider scope"):
        await env.provider.invoke("messages.send", {"user_id": "me", "raw": "hi"})


@pytest.mark.asyncio
async def test_both_gates_passing_lets_the_call_through(env, vendor) -> None:
    await env.grant("network")
    env.store_credential(scopes=("vendor.read",))
    await env.provider.start()

    result = await env.provider.invoke("messages.list", {"user_id": "me", "q": "hello"})

    assert result.ok
    assert result.data["messages"][0]["id"] == "m1"
    assert vendor.seen[0].query["q"] == "hello"


@pytest.mark.asyncio
async def test_the_refusal_names_which_gate_said_no(env) -> None:
    """ "permission not granted" and "the token lacks that scope" call
    for completely different fixes."""
    env.store_credential()
    await env.provider.start()

    with pytest.raises(IntegrationError) as caught:
        await env.provider.invoke("messages.list", {"user_id": "me"})

    assert "JARVIS permission" in str(caught.value)


@pytest.mark.asyncio
async def test_a_second_jarvis_scope_is_required_when_declared(env) -> None:
    """files.get declares filesystem as well as network."""
    await env.grant("network")
    env.store_credential()
    await env.provider.start()

    with pytest.raises(IntegrationError, match="filesystem"):
        await env.provider.invoke("files.get", {"file_id": "f1"})


@pytest.mark.asyncio
async def test_a_revoked_grant_takes_effect_on_the_next_call(env) -> None:
    """Checked per call rather than cached at connect, so revoking does
    not need a reconnect to bite."""
    await env.grant("network")
    env.store_credential()
    await env.provider.start()
    await env.provider.invoke("messages.list", {"user_id": "me"})

    await env.permissions.deny(principal_for("acme_mail"), "network")

    with pytest.raises(IntegrationError, match="permission"):
        await env.provider.invoke("messages.list", {"user_id": "me"})


@pytest.mark.asyncio
async def test_an_unauthenticated_provider_is_refused_at_the_gate(env) -> None:
    await env.grant("network")
    env.store_credential()
    await env.provider.start()
    env.store.delete("acme_mail", persist=False)

    with pytest.raises(IntegrationError, match="not authenticated"):
        await env.provider.invoke("messages.list", {"user_id": "me"})


@pytest.mark.asyncio
async def test_invoking_a_disconnected_provider_is_refused(env) -> None:
    await env.grant("network")
    env.store_credential()
    await env.provider.initialize()

    with pytest.raises(IntegrationError, match="not connected"):
        await env.provider.invoke("messages.list", {"user_id": "me"})


@pytest.mark.asyncio
async def test_an_unknown_operation_is_refused_before_any_gate(env) -> None:
    with pytest.raises(IntegrationError, match="has no operation"):
        await env.provider.invoke("messages.telepathy", {})


# --- request construction -------------------------------------------------------


@pytest.mark.asyncio
async def test_build_request_resolves_the_url_without_sending(env, vendor) -> None:
    """An outbound call cannot be undone by asserting on it
    afterwards."""
    await env.provider.initialize()
    env.store_credential()

    request = env.provider.build_request("messages.list", {"user_id": "me", "q": "hi"})

    assert request.url.endswith("/v1/users/me/messages")
    assert request.query == {"q": "hi"}
    assert request.method == "GET"
    assert vendor.seen == []


@pytest.mark.asyncio
async def test_build_request_attaches_the_bearer_header(env) -> None:
    env.store_credential()
    request = env.provider.build_request("messages.list", {"user_id": "me"})

    assert request.headers["Authorization"] == "Bearer at-1"


@pytest.mark.asyncio
async def test_build_request_attaches_nothing_without_a_credential(env) -> None:
    request = env.provider.build_request("messages.list", {"user_id": "me"})
    assert request.headers == {}


@pytest.mark.asyncio
async def test_the_account_key_separates_two_accounts_caches(env) -> None:
    other = RestIntegrationProvider(
        env.spec, gateway=env.gateway, auth_manager=env.auth, account_id="someone-else"
    )

    mine = env.provider.build_request("messages.list", {"user_id": "me"})
    theirs = other.build_request("messages.list", {"user_id": "me"})

    assert mine.cache_key() != theirs.cache_key()


@pytest.mark.asyncio
async def test_a_mutating_request_is_marked_uncacheable(env) -> None:
    env.store_credential()
    request = env.provider.build_request("messages.send", {"user_id": "me", "raw": "hi"})

    assert request.cacheable is False
    assert request.mutating is True
    assert request.body == {"raw": "hi"}


# --- refresh --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_nearly_expired_credential_is_refreshed_before_the_call(env, vendor) -> None:
    """Refreshing after a 401 would leave the caller unable to tell an
    expired token from a revoked grant."""
    refreshed: list[str] = []

    class _Bound:
        method = AuthMethod.OAUTH2

        async def refresh(self, credential):
            refreshed.append(credential.provider_id)
            return credential.with_refreshed(
                "at-2", expires_at=datetime.now(UTC) + timedelta(hours=1)
            )

        async def revoke(self, credential):
            return credential.revoke()

        def validate(self, credential):
            return credential.is_valid()

    await env.grant("network")
    env.store_credential(expires_at=datetime.now(UTC) + timedelta(seconds=10))
    env.auth.bind_strategy("acme_mail", _Bound())
    await env.provider.start()

    await env.provider.invoke("messages.list", {"user_id": "me"})

    assert refreshed == ["acme_mail"]
    assert vendor.seen[0].headers["Authorization"] == "Bearer at-2"


@pytest.mark.asyncio
async def test_a_failing_refresh_does_not_block_the_call(env) -> None:
    """If the token really is dead the vendor says so, and that names
    the vendor's own reason -- more useful than guessing in advance."""

    class _Broken:
        method = AuthMethod.OAUTH2

        async def refresh(self, credential):
            raise RuntimeError("refresh endpoint down")

        async def revoke(self, credential):
            return credential.revoke()

        def validate(self, credential):
            return credential.is_valid()

    await env.grant("network")
    env.store_credential(expires_at=datetime.now(UTC) + timedelta(seconds=10))
    env.auth.bind_strategy("acme_mail", _Broken())
    await env.provider.start()

    result = await env.provider.invoke("messages.list", {"user_id": "me"})

    assert result.ok


# --- health and status ----------------------------------------------------------


@pytest.mark.asyncio
async def test_health_is_local_and_never_calls_the_vendor(env, vendor) -> None:
    """HealthMonitor polls this on a cadence; reaching the network would
    turn a health poll into quota spend."""
    env.store_credential()
    await env.provider.start()

    for _ in range(3):
        assert (await env.provider.health()).healthy is True

    assert vendor.seen == []


@pytest.mark.asyncio
async def test_health_reports_an_uninitialized_provider(env) -> None:
    status = await env.provider.health()
    assert status.healthy is False
    assert "not initialized" in status.detail


@pytest.mark.asyncio
async def test_health_reports_a_revoked_credential(env) -> None:
    env.store_credential()
    await env.provider.start()
    env.store.put(env.store.get("acme_mail").revoke(), persist=False)

    status = await env.provider.health()

    assert status.healthy is False
    assert "revoked" in status.detail


@pytest.mark.asyncio
async def test_status_reports_scopes_counts_and_never_a_token(env) -> None:
    await env.grant("network")
    env.store_credential()
    await env.provider.start()
    await env.provider.invoke("messages.list", {"user_id": "me"})

    status = await env.provider.status()

    assert status.detail["calls"] == 1
    assert status.detail["authenticated"] is True
    assert status.detail["required_vendor_scopes"] == ["vendor.read", "vendor.send"]
    assert "at-1" not in str(status.detail)


@pytest.mark.asyncio
async def test_a_vendor_error_counts_as_a_failure(env, aiohttp_server, tmp_path) -> None:
    async def failing(_request: web.Request) -> web.Response:
        return web.json_response({"error": {"message": "nope"}}, status=403)

    app = web.Application()
    app.router.add_get("/v1/users/{user_id}/messages", failing)
    server = await aiohttp_server(app)

    broken = _Env(tmp_path / "broken", str(server.make_url("")).rstrip("/"))
    (tmp_path / "broken").mkdir(exist_ok=True)
    await broken.grant("network")
    broken.store_credential()
    await broken.provider.start()

    try:
        with pytest.raises(GatewayError):
            await broken.provider.invoke("messages.list", {"user_id": "me"})
        status = await broken.provider.status()
        assert status.detail["failures"] == 1
    finally:
        await broken.gateway.stop()
