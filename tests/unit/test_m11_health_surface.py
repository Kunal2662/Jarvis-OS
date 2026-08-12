"""M11 Task Group C -- API Center Health Surface tests.

Proves the health/connection-test boundary in
``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §11/§13 is real: health is
local-only, never a vendor request, uses the project's existing
``HealthStatus``/``ProviderState`` vocabulary (no new health enum),
rides the existing single ``HealthMonitor`` ``mcp`` collector rather
than a second one, and never leaks a credential value.

No ``unittest.mock``, no HTTP-library patching -- a real local
``aiohttp`` fake-vendor server proves the "no network call" guarantee,
matching ``tests/unit/test_integration_provider.py``'s own convention
(``vendor.seen == []``).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from jarvis.core.config.settings import Settings
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
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
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.integration_service import IntegrationService

_GOOGLE_GMAIL = "google_gmail"
_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "jarvis"


# ---------------------------------------------------------------------------
# Shared real-component environment, using the real Google Workspace
# catalogue entry -- install/initialize/connect never touch the network
# by the codebase's own design (see provider.py's docstrings and
# test_integration_provider.py's existing "touches no network" tests),
# so no fake vendor server is needed for these end-to-end checks.
# ---------------------------------------------------------------------------


@pytest.fixture()
def env(tmp_path: Path):
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    credential_store = CredentialStore(tmp_path / "mcp_credentials.json", secret_key="")
    auth_manager = MCPAuthManager(
        credential_store, build_default_strategy_registry(), permissions, event_bus=bus
    )
    provider_registry = MCPProviderRegistry()
    provider_manager = MCPProviderManager(
        provider_registry,
        client_runtime=MCPClientRuntime(),
        transport_registry=TransportFactoryRegistry(),
        permission_model=permissions,
        event_bus=bus,
    )
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    settings = Settings(data_dir=tmp_path)
    integration_service = IntegrationService(
        provider_manager=provider_manager,
        auth_manager=auth_manager,
        gateway=gateway,
        settings=settings,
    )
    return {
        "service": integration_service,
        "provider_manager": provider_manager,
        "auth": auth_manager,
        "store": credential_store,
    }


def _store_credential(store: CredentialStore, integration_id: str, **kwargs: object) -> None:
    defaults: dict[str, object] = {
        "provider_id": integration_id,
        "method": AuthMethod.OAUTH2,
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "scopes": (),
    }
    defaults.update(kwargs)
    store.put(Credential(**defaults), persist=False)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 1 + 3. Local health / unknown state -- installed but never connected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_installed_but_unconnected_integration_is_not_reported_healthy(env: dict) -> None:
    """No evidence of a working connection yet -- must not be HEALTHY.
    The existing vocabulary's equivalent of "unknown": state stays
    'initialized' (installed, never connected), healthy is False --
    never manufactured."""
    await env["service"].install(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)

    assert health["integration_id"] == _GOOGLE_GMAIL
    assert health["vendor"] == "google"
    assert health["state"] == "initialized"
    assert health["healthy"] is False
    assert health["credential_status"] == "missing"
    assert health["credential_configured"] is False


@pytest.mark.asyncio
async def test_health_for_an_uninstalled_integration_is_a_service_error(env: dict) -> None:
    """Matches the existing convention every other per-integration route
    already uses (status/connect/invoke) -- not silently "unknown"."""
    with pytest.raises(ServiceError):
        await env["service"].health("not_installed_at_all")


# ---------------------------------------------------------------------------
# Healthy / 4. local failure / 5. local recovery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connected_integration_with_valid_credential_is_healthy(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)

    assert health["state"] == "connected"
    assert health["healthy"] is True
    assert health["credential_configured"] is True
    assert health["credential_status"] == "active"


@pytest.mark.asyncio
async def test_revoked_credential_is_a_local_failure(env: dict) -> None:
    """A locally-known failure -- no vendor call needed to know a
    revoked credential can no longer authenticate."""
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)
    assert (await env["service"].health(_GOOGLE_GMAIL))["healthy"] is True

    await env["auth"].revoke(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["healthy"] is False
    assert health["credential_status"] == "revoked"


@pytest.mark.asyncio
async def test_storing_a_fresh_credential_is_a_local_recovery(env: dict) -> None:
    """Local recovery: a fresh credential flips health back without any
    vendor involvement."""
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)
    await env["auth"].revoke(_GOOGLE_GMAIL)
    assert (await env["service"].health(_GOOGLE_GMAIL))["healthy"] is False

    _store_credential(env["store"], _GOOGLE_GMAIL, access_token="at-2", refresh_token="rt-2")

    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["healthy"] is True
    assert health["credential_status"] == "active"


# ---------------------------------------------------------------------------
# 6. Credential safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_output_never_exposes_credential_values(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL, access_token="super-secret-access-token")
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)

    serialized = repr(health)
    assert "super-secret-access-token" not in serialized
    assert "rt-1" not in serialized
    assert "Bearer" not in serialized
    assert "access_token" not in health
    assert "refresh_token" not in health
    assert not {k for k in health if "authorization" in k.lower()}


# ---------------------------------------------------------------------------
# 7. Reuses the existing HealthMonitor channel -- no second collector
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_integration_health_rides_the_existing_provider_manager_collector(
    env: dict,
) -> None:
    """No second collector is registered for M11: the same
    ``MCPProviderManager.collect_health()`` the existing ``mcp``
    ``HealthMonitor`` collector already uses (``app.py``) includes this
    integration too, because it is registered through the same
    ``MCPProviderManager``/``MCPProviderRegistry`` as any other
    provider."""
    await env["service"].install(_GOOGLE_GMAIL)

    snapshot = await env["provider_manager"].collect_health()

    provider_ids = {p["provider_id"] for p in snapshot["providers"]}
    assert _GOOGLE_GMAIL in provider_ids


# ---------------------------------------------------------------------------
# 8. AI Calibration boundary -- the new route file stays clean too
# ---------------------------------------------------------------------------


def test_health_route_never_references_illm_provider_or_ai_routing() -> None:
    text = (_SRC_ROOT / "infrastructure" / "api" / "routes" / "integrations.py").read_text(
        encoding="utf-8"
    )
    for needle in ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider"):
        assert needle not in text


# ---------------------------------------------------------------------------
# 2. No external call -- would fail if a real vendor request were made
# ---------------------------------------------------------------------------


def _synthetic_spec(base_url: str) -> IntegrationSpec:
    return IntegrationSpec(
        integration_id="acme_health_probe",
        name="Acme Health Probe",
        vendor="acme",
        base_url=base_url,
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
        ),
        operations=(
            OperationSpec(name="ping", method="GET", path="/ping", permissions=("network",)),
        ),
    )


@pytest.fixture()
async def vendor_server(aiohttp_server):
    """A fake vendor that records every request it receives. A health
    check must never produce one -- this fixture is what would make
    such a regression fail the test below."""
    seen: list[web.Request] = []

    async def ping(request: web.Request) -> web.Response:
        seen.append(request)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/ping", ping)
    server = await aiohttp_server(app)
    server.seen = seen  # type: ignore[attr-defined]
    return server


@pytest.mark.asyncio
async def test_health_check_makes_zero_requests_to_the_vendor(
    tmp_path: Path, vendor_server
) -> None:
    """Exercises the exact call chain ``IntegrationService.health()``
    uses (``MCPProviderManager.health()`` -> ``RestIntegrationProvider.
    health()``) directly against a real local vendor stand-in, across
    every state this task group implements: unconnected, connected, and
    locally revoked. ``vendor_server.seen`` staying empty is the proof;
    it would not if ``health()`` ever regressed into a real request."""
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    spec = _synthetic_spec(str(vendor_server.make_url("")).rstrip("/"))
    provider = RestIntegrationProvider(spec, gateway=gateway, auth_manager=auth, account_id="me")

    try:
        await provider.health()  # unconnected, no credential

        _store_credential(store, spec.integration_id)
        await provider.start()
        await provider.health()  # connected, valid credential

        await auth.revoke(spec.integration_id)
        await provider.health()  # locally revoked
    finally:
        await gateway.stop()

    assert vendor_server.seen == []
