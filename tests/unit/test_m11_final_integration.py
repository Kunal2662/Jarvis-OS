"""M11 Task Group G -- Final REST, Events, Observability & Integration
Validation.

Three concerns, deliberately kept in one file because they are all
*cross-cutting* checks over the finished M11 surface rather than one
more mechanism's own unit tests (each mechanism already has its own
dedicated file from Task Groups A-F):

1. Observability -- the new counters/snapshot are correct and secret-free.
2. REST/event validation -- every ``/integrations/*`` route requires a
   session (enumerated programmatically, not from a hand-maintained
   list, so a future route added without auth fails this test), and
   every M11 event class is structurally secret-free.
3. Integration validation -- one continuous flow exercising every task
   group's mechanism together (discover -> connect -> health ->
   connection test -> invoke -> switch -> failover -> disconnect),
   proving they compose, not just that each works in isolation.

No ``unittest.mock``. Real local ``aiohttp`` fake-vendor servers for
anything that needs controlled vendor behavior.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
from aiohttp import web

from jarvis.core.config.settings import Settings
from jarvis.core.events import events as events_module
from jarvis.core.events.event_bus import EventBus
from jarvis.core.integrations.gateway import ApiGateway
from jarvis.core.integrations.models import AuthSpec, IntegrationSpec, OperationSpec
from jarvis.core.integrations.provider import RestIntegrationProvider
from jarvis.core.mcp.auth.credentials import AuthMethod, Credential
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.server import principal_for
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.integration_service import IntegrationService

_OPERATION = "status.get"


def _spec(integration_id: str, base_url: str) -> IntegrationSpec:
    return IntegrationSpec(
        integration_id=integration_id,
        name=integration_id,
        vendor="acme",
        base_url=base_url,
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
        ),
        operations=(
            OperationSpec(
                name=_OPERATION,
                method="GET",
                path="/probe",
                category="read",
                permissions=("network",),
                scopes=("vendor.read",),
            ),
        ),
    )


def _store_credential(store: CredentialStore, integration_id: str, **kwargs: object) -> None:
    defaults: dict[str, object] = {
        "provider_id": integration_id,
        "method": AuthMethod.OAUTH2,
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "scopes": ("vendor.read",),
    }
    defaults.update(kwargs)
    store.put(Credential(**defaults), persist=False)  # type: ignore[arg-type]


class _Vendor:
    def __init__(self) -> None:
        self.mode = "success"
        self.requests_seen: list[web.Request] = []

    async def handler(self, request: web.Request) -> web.Response:
        self.requests_seen.append(request)
        if self.mode == "success":
            return web.json_response({"ok": True})
        return web.json_response({"error": "internal"}, status=500)


@pytest.fixture()
async def primary_vendor(aiohttp_server):
    v = _Vendor()
    app = web.Application()
    app.router.add_get("/probe", v.handler)
    server = await aiohttp_server(app)
    server.vendor = v  # type: ignore[attr-defined]
    return server


@pytest.fixture()
async def alternate_vendor(aiohttp_server):
    v = _Vendor()
    app = web.Application()
    app.router.add_get("/probe", v.handler)
    server = await aiohttp_server(app)
    server.vendor = v  # type: ignore[attr-defined]
    return server


@pytest.fixture()
async def env(tmp_path: Path, primary_vendor, alternate_vendor):
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    registry = MCPProviderRegistry()
    manager = MCPProviderManager(
        registry,
        client_runtime=MCPClientRuntime(),
        transport_registry=TransportFactoryRegistry(),
        permission_model=permissions,
        event_bus=bus,
    )
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    await gateway.start()
    settings = Settings(data_dir=tmp_path)
    service = IntegrationService(
        provider_manager=manager,
        auth_manager=auth,
        gateway=gateway,
        settings=settings,
        event_bus=bus,
    )

    primary_spec = _spec("acme_primary", str(primary_vendor.make_url("")).rstrip("/"))
    alternate_spec = _spec("acme_alternate", str(alternate_vendor.make_url("")).rstrip("/"))
    primary = RestIntegrationProvider(primary_spec, gateway=gateway, auth_manager=auth)
    alternate = RestIntegrationProvider(alternate_spec, gateway=gateway, auth_manager=auth)

    for provider_id, spec, provider in (
        ("acme_primary", primary_spec, primary),
        ("acme_alternate", alternate_spec, alternate),
    ):
        await manager.install(provider_id, spec.to_metadata(), provider=provider)
        await manager.initialize(provider_id)
        service._installed[provider_id] = provider
        principal = principal_for(provider_id)
        permissions.declare(principal, ["network"])
        await permissions.grant(principal, "network")

    try:
        yield {
            "service": service,
            "registry": registry,
            "primary_vendor": primary_vendor.vendor,
            "alternate_vendor": alternate_vendor.vendor,
        }
    finally:
        await gateway.stop()


# ===========================================================================
# 1. Observability
# ===========================================================================


@pytest.mark.asyncio
async def test_observability_snapshot_starts_at_zero(env: dict) -> None:
    snapshot = env["service"].observability_snapshot()

    assert snapshot["connection_test_count"] == 0
    assert snapshot["switch_count"] == 0
    assert snapshot["failover_recovered_count"] == 0
    assert snapshot["discovery_run_count"] == 0
    assert snapshot["installed_count"] == 2  # the env fixture's two synthetic integrations
    assert "gateway" in snapshot


@pytest.mark.asyncio
async def test_observability_counters_increment_with_real_operations(env: dict) -> None:
    _store_credential_via_auth(env)

    await env["service"].test_connection("acme_primary", operation=_OPERATION)
    await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    snapshot = env["service"].observability_snapshot()
    assert snapshot["connection_test_count"] == 1
    assert snapshot["connection_test_success_count"] == 1
    assert snapshot["switch_count"] == 1
    assert snapshot["switch_success_count"] == 1
    assert snapshot["connected_count"] >= 1


def _store_credential_via_auth(env: dict) -> None:
    from jarvis.core.mcp.auth.credentials import AuthMethod, Credential

    for integration_id in ("acme_primary", "acme_alternate"):
        env["service"]._auth._store.put(
            Credential(
                provider_id=integration_id,
                method=AuthMethod.OAUTH2,
                access_token="at-1",
                refresh_token="rt-1",
                scopes=("vendor.read",),
            ),
            persist=False,
        )


def test_observability_snapshot_never_carries_a_credential(env: dict) -> None:
    snapshot = env["service"].observability_snapshot()

    assert "access_token" not in repr(snapshot)
    assert "refresh_token" not in repr(snapshot)


# ===========================================================================
# 2a. REST validation -- every /integrations/* route requires a session,
#     enumerated programmatically from the real router, not a hand list.
# ===========================================================================


def test_every_integrations_route_is_behind_session_auth() -> None:
    from jarvis.infrastructure.api.auth import get_current_session
    from jarvis.infrastructure.api.routes.integrations import router

    for route in router.routes:
        dependant = getattr(route, "dependant", None)
        dependency_calls = {d.call for d in (dependant.dependencies if dependant else [])}
        assert (
            get_current_session in dependency_calls
        ), f"{route.path} ({route.methods}) is missing the session dependency"


def test_the_callback_router_remains_the_only_session_free_route() -> None:
    """Pins the one deliberate exception (see integrations.py's own
    module docstring) so a future route added to the wrong router is
    caught here, not discovered as a security gap."""
    from jarvis.infrastructure.api.routes.integrations import callback_router

    paths = {route.path for route in callback_router.routes}
    assert paths == {"/integrations/oauth/callback"}


# ===========================================================================
# 2b. Event validation -- every M11 event is structurally secret-free
# ===========================================================================


_M11_EVENT_CLASSES = (
    events_module.IntegrationCallCompletedEvent,
    events_module.IntegrationConnectionTestEvent,
    events_module.IntegrationSwitchEvent,
    events_module.IntegrationFailoverEvent,
    events_module.IntegrationDiscoveryEvent,
)

_FORBIDDEN_FIELD_SUBSTRINGS = ("token", "secret", "password", "authorization", "credential")


def test_no_m11_event_declares_a_secret_shaped_field() -> None:
    for event_cls in _M11_EVENT_CLASSES:
        for f in dataclasses.fields(event_cls):
            lowered = f.name.lower()
            assert not any(
                needle in lowered for needle in _FORBIDDEN_FIELD_SUBSTRINGS
            ), f"{event_cls.__name__}.{f.name} looks secret-shaped"


def test_every_m11_event_is_relayed_or_documented_absent() -> None:
    """Delegates to the project's own pinned vocabulary invariant
    (test_platform_integration.py) for the *mechanism*; this asserts
    the M11-specific slice of it explicitly, so an M11 regression is
    diagnosed here rather than in an unrelated file."""
    from jarvis.core.lifecycle.runtime_ws_hub import EVENT_TYPE_NAMES, UNPUBLISHED_EVENT_TYPES

    for event_cls in _M11_EVENT_CLASSES:
        accounted_for = (
            event_cls in EVENT_TYPE_NAMES or event_cls.__name__ in UNPUBLISHED_EVENT_TYPES
        )
        assert accounted_for, f"{event_cls.__name__} is neither relayed nor documented as absent"


# ===========================================================================
# 3. Full end-to-end integration validation
# ===========================================================================


@pytest.mark.asyncio
async def test_full_lifecycle_discover_connect_test_invoke_switch_failover_disconnect(
    env: dict,
) -> None:
    """Every M11 task group's mechanism, chained in one flow, against
    the two synthetic integrations the ``env`` fixture already
    registered (Task Group D's install(), reused here exactly as
    Task Group F's discover() itself reuses it)."""
    service = env["service"]
    _store_credential_via_auth(env)

    # -- Activation (Task Group D) --
    await service.connect("acme_primary")
    assert env["registry"].get("acme_primary").state.value == "connected"

    # -- Health (Task Group C) -- local-only --
    health = await service.health("acme_primary")
    assert health["healthy"] is True
    assert env["primary_vendor"].requests_seen == []

    # -- Connection Test (Task Group B) -- one real, bounded request --
    test_result = await service.test_connection("acme_primary", operation=_OPERATION)
    assert test_result["outcome"] == "success"
    assert len(env["primary_vendor"].requests_seen) == 1

    # -- Invoke (pre-M11 baseline call path) -- served from the
    # gateway's own existing response cache (same operation, same
    # account, same params as the Connection Test just above -- the
    # gateway's cache existed before Task Group B and is correctly
    # doing its job here, not a Task Group B/G interaction to work
    # around).
    invoke_result = await service.invoke("acme_primary", _OPERATION)
    assert invoke_result["status_code"] == 200
    assert invoke_result["from_cache"] is True
    assert len(env["primary_vendor"].requests_seen) == 1

    # -- Runtime Switching (Task Group E) --
    switch_result = await service.switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )
    assert switch_result["outcome"] == "success"
    assert env["registry"].get("acme_alternate").state.value == "connected"
    assert env["registry"].get("acme_primary").state.value == "disconnected"

    # -- Failover (Task Group E) -- primary is down, alternate recovers --
    # The switch above deactivated the primary; invoke() (which
    # invoke_with_failover() calls first) requires its own provider to
    # be connected, so it is reactivated here -- a legitimate, ordinary
    # reconnect, not a special case invented for this test. The
    # gateway's own pre-existing response cache (see the invoke() step
    # above) still holds the primary's earlier successful result, so it
    # is explicitly invalidated here too -- the real, existing
    # ApiGateway.invalidate() API, standing in for the 30s TTL that
    # would otherwise simply elapse in production; without this the
    # cached success would mask the vendor failure this step means to
    # exercise.
    await service.connect("acme_primary")
    service._gateway.invalidate()
    env["primary_vendor"].mode = "500"
    failover_result = await service.invoke_with_failover(
        "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
    )
    assert failover_result["integration_id"] == "acme_alternate"
    assert failover_result["failed_over_from"] == "acme_primary"

    # -- Deactivation (Task Group D) --
    disconnected = await service.disconnect("acme_alternate")
    assert disconnected is True
    assert env["registry"].get("acme_alternate").state.value == "disconnected"

    # -- Observability reflects the whole flow --
    snapshot = service.observability_snapshot()
    assert snapshot["connection_test_count"] == 1
    assert snapshot["switch_count"] == 1
    assert snapshot["switch_success_count"] == 1
    assert snapshot["failover_recovered_count"] == 1

    # -- Discovery (Task Group F) -- discover() only ever enumerates the
    # real catalogue (never these synthetic test integrations, which
    # were never in it to begin with); it must run cleanly alongside
    # them and must not disturb either synthetic integration's state.
    discovery_results = await service.discover()
    assert len(discovery_results) == 11  # the real Google Workspace catalogue
    assert all(r["status"] == "registered" for r in discovery_results)
    assert env["registry"].get("acme_alternate").state.value == "disconnected"

    # -- Credentials were never modified across the whole flow --
    assert service._auth._store.get("acme_primary").access_token == "at-1"
    assert service._auth._store.get("acme_alternate").access_token == "at-1"
