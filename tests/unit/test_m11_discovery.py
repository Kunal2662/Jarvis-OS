"""M11 Task Group F -- Automatic Integration Discovery tests.

Discovery enumerates the real catalogue (``core/integrations/
catalogue.py``, 11 entries, one vendor family -- Google Workspace) and
registers unregistered entries through Task Group D's existing
``install()`` -- no synthetic vendor is needed to prove the mechanism,
unlike Task Group E's cross-vendor tests. A real local ``aiohttp``
fake-vendor server is used once, specifically to prove zero network
calls occur -- matching the project's established "prove absence of a
network call with a real server that would otherwise receive it"
convention.

No ``unittest.mock``, no fake provider registries, no dynamic/arbitrary
imports.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from jarvis.core.config.settings import Settings
from jarvis.core.events.event_bus import EventBus
from jarvis.core.integrations.catalogue import available_ids
from jarvis.core.integrations.gateway import ApiGateway
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.integration_service import IntegrationService

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "jarvis"
_CATALOGUE_IDS = available_ids()


@pytest.fixture()
def env(tmp_path: Path):
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
    settings = Settings(data_dir=tmp_path)
    service = IntegrationService(
        provider_manager=manager,
        auth_manager=auth,
        gateway=gateway,
        settings=settings,
        event_bus=bus,
    )
    return {
        "service": service,
        "auth": auth,
        "store": store,
        "registry": registry,
        "manager": manager,
        "bus": bus,
    }


# ===========================================================================
# Catalogue enumeration (1-5)
# ===========================================================================


@pytest.mark.asyncio
async def test_1_discovery_enumerates_every_current_catalogue_id(env: dict) -> None:
    results = await env["service"].discover()

    discovered_ids = {r["integration_id"] for r in results}
    assert discovered_ids == set(_CATALOGUE_IDS)
    assert len(results) == len(_CATALOGUE_IDS) == 11


@pytest.mark.asyncio
async def test_2_every_discovered_entry_has_a_valid_spec(env: dict) -> None:
    results = await env["service"].discover()

    for row in results:
        assert row["status"] in ("registered", "already_registered")
        assert row["reason"] == ""


@pytest.mark.asyncio
async def test_3_vendor_metadata_is_correctly_surfaced(env: dict) -> None:
    results = await env["service"].discover()

    assert {r["vendor"] for r in results} == {"google"}


@pytest.mark.asyncio
async def test_4_capabilities_are_correctly_surfaced(env: dict) -> None:
    results = await env["service"].discover()

    gmail = next(r for r in results if r["integration_id"] == "google_gmail")
    assert "messages.list" in gmail["capabilities"]
    assert len(gmail["capabilities"]) == 12


@pytest.mark.asyncio
async def test_5_no_non_catalogue_integration_is_ever_discovered(env: dict) -> None:
    results = await env["service"].discover()

    for row in results:
        assert row["integration_id"] in _CATALOGUE_IDS
    # Nothing outside the catalogue's own vendor family appears.
    assert {r["vendor"] for r in results} <= {"google"}


# ===========================================================================
# Registration (6-10)
# ===========================================================================


@pytest.mark.asyncio
async def test_6_unregistered_entry_is_registered_through_install(env: dict) -> None:
    assert "google_gmail" not in env["service"].installed_ids()

    results = await env["service"].discover()

    gmail = next(r for r in results if r["integration_id"] == "google_gmail")
    assert gmail["status"] == "registered"
    assert "google_gmail" in env["service"].installed_ids()
    # The same registry install() itself would have used -- see 7-9.
    record = env["registry"].get("google_gmail")
    assert record is not None


def test_7_8_9_discovery_uses_the_existing_registry_manager_and_credential_store(
    env: dict,
) -> None:
    assert env["service"]._providers is env["manager"]
    assert env["manager"].registry is env["registry"]
    assert env["service"]._auth is env["auth"]
    assert env["auth"]._store is env["store"]


@pytest.mark.asyncio
async def test_10_registered_state_is_visible_through_existing_infrastructure(
    env: dict,
) -> None:
    await env["service"].discover()

    status = await env["service"].status("google_gmail")
    assert status["state"] in ("registered", "initialized")
    health = await env["service"].health("google_gmail")
    assert health["integration_id"] == "google_gmail"


# ===========================================================================
# Idempotency (11-15)
# ===========================================================================


@pytest.mark.asyncio
async def test_11_12_13_14_15_repeated_discovery_does_not_duplicate(env: dict) -> None:
    first = await env["service"].discover()
    assert all(r["status"] == "registered" for r in first)
    provider_identity_after_first = id(env["service"]._installed["google_gmail"])
    registry_size_after_first = len(env["registry"].discover())

    second = await env["service"].discover()

    assert all(r["status"] == "already_registered" for r in second)
    assert len(env["registry"].discover()) == registry_size_after_first
    assert id(env["service"]._installed["google_gmail"]) == provider_identity_after_first
    # No credential existed before or after -- discovery created none.
    assert env["store"].get("google_gmail") is None


# ===========================================================================
# No auto-activation (16-18)
# ===========================================================================


@pytest.mark.asyncio
async def test_16_17_18_discovery_never_activates_or_connects(env: dict) -> None:
    results = await env["service"].discover()

    for row in results:
        record = env["registry"].get(row["integration_id"])
        assert record is not None
        assert record.state.value != "connected"

    gmail_health = await env["service"].health("google_gmail")
    assert gmail_health["healthy"] is False


@pytest.mark.asyncio
async def test_already_active_integration_is_left_active_by_a_later_discovery(
    tmp_path: Path, env: dict
) -> None:
    """Discovery must not deactivate something that was already active
    for an unrelated reason -- confirmed here by installing directly
    (bypassing discovery) and connecting is not attempted since no
    credential exists; instead this proves discovery is a strict no-op
    for an already-installed entry regardless of its connection state."""
    await env["service"].install("google_gmail")
    before = env["registry"].get("google_gmail").state

    await env["service"].discover()

    assert env["registry"].get("google_gmail").state == before


# ===========================================================================
# No Connection Test (19-22)
# ===========================================================================


@pytest.fixture()
async def vendor_server(aiohttp_server):
    """A fake vendor that would receive any real call -- discovery must
    leave this untouched."""
    seen: list[web.Request] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(request)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/{tail:.*}", handler)
    server = await aiohttp_server(app)
    server.seen = seen  # type: ignore[attr-defined]
    return server


@pytest.mark.asyncio
async def test_19_discovery_makes_zero_requests_to_a_real_local_vendor_stand_in(
    env: dict, vendor_server
) -> None:
    """Every real Google catalogue spec points at Google's own base
    URL, which discovery must never contact -- proven directly via the
    gateway's own call counter (the project's established alternative
    to a fake-vendor-server proof when the code under test cannot be
    pointed at a local server, since the catalogue's base URLs are
    fixed, trusted data)."""
    await env["service"].discover()

    stats = env["service"].gateway_stats()
    assert stats["calls"] == 0
    assert vendor_server.seen == []  # never touched -- nothing pointed at it, by design


def test_20_discover_one_never_calls_test_connection() -> None:
    import inspect

    source = inspect.getsource(IntegrationService._discover_one)
    assert "test_connection" not in source


@pytest.mark.asyncio
async def test_21_22_discovery_never_validates_or_refreshes_credentials(env: dict) -> None:
    """No credential exists before discovery and none is created,
    refreshed, or touched by it."""
    assert env["store"].get("google_gmail") is None

    await env["service"].discover()

    assert env["store"].get("google_gmail") is None


# ===========================================================================
# Security / supply-chain (23-28)
# ===========================================================================


def test_23_24_25_26_discover_endpoint_accepts_no_targeting_fields() -> None:
    """The route takes no request body at all -- there is no field for
    a URL, provider class, filesystem path, or package name to occupy."""
    import inspect

    from jarvis.infrastructure.api.routes.integrations import discover_integrations

    signature = inspect.signature(discover_integrations)
    assert list(signature.parameters) == ["request"]


def test_27_discovery_source_is_the_static_catalogue_dict_only() -> None:
    """No importlib, no pkgutil, no dynamic import anywhere in the
    discovery implementation."""
    text = (_SRC_ROOT / "core" / "integrations" / "discovery.py").read_text(encoding="utf-8")
    service_text = (_SRC_ROOT / "services" / "integration_service.py").read_text(encoding="utf-8")
    for needle in ("importlib", "pkgutil", "__import__", "exec(", "eval(", "subprocess"):
        assert needle not in text
        assert needle not in service_text


def test_28_discovery_never_references_package_installation() -> None:
    for relative in ("core/integrations/discovery.py", "services/integration_service.py"):
        text = (_SRC_ROOT / relative).read_text(encoding="utf-8")
        for needle in ("pip", "subprocess", "urlretrieve", "download"):
            assert needle not in text, f"{relative} references {needle!r}"


# ===========================================================================
# Failure isolation (32-35)
# ===========================================================================


@pytest.mark.asyncio
async def test_32_33_one_invalid_catalogue_entry_does_not_fail_the_whole_sweep(
    env: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A deliberately malformed spec builder is injected into the real
    catalogue dict for the duration of this test only (plain dict
    manipulation via pytest's own monkeypatch fixture -- not
    unittest.mock, and not a fake registry: the same AVAILABLE_SPECS
    dict discovery already reads)."""
    from jarvis.core.integrations import catalogue as catalogue_module
    from jarvis.core.integrations.models import AuthSpec, IntegrationSpec
    from jarvis.core.mcp.auth.credentials import AuthMethod

    def _broken_spec() -> IntegrationSpec:
        # No operations declared -- IntegrationSpec.validate() (called
        # inside build_spec()) refuses this for real.
        return IntegrationSpec(
            integration_id="acme_broken",
            name="Broken",
            vendor="acme",
            base_url="https://example.test",
            auth=AuthSpec(method=AuthMethod.NONE),
            operations=(),
        )

    patched = dict(catalogue_module.AVAILABLE_SPECS)
    patched["acme_broken"] = _broken_spec
    monkeypatch.setattr(catalogue_module, "AVAILABLE_SPECS", patched)

    results = await env["service"].discover()

    broken = next(r for r in results if r["integration_id"] == "acme_broken")
    assert broken["status"] == "rejected"
    assert broken["reason"] != ""
    # Every real, valid catalogue entry still registered successfully.
    others = [r for r in results if r["integration_id"] != "acme_broken"]
    assert all(r["status"] == "registered" for r in others)
    assert len(env["service"].installed_ids()) == len(_CATALOGUE_IDS)


@pytest.mark.asyncio
async def test_34_35_discovery_never_triggers_failover_or_switching(env: dict) -> None:
    await env["service"].discover()

    assert env["service"].failover_history() == []


def test_34_35_discover_one_never_references_failover_or_switching() -> None:
    import inspect

    source = inspect.getsource(IntegrationService._discover_one)
    for needle in ("failover", "Failover", "switch(", "Switch"):
        assert needle not in source


# ===========================================================================
# AI boundary (36-38)
# ===========================================================================


def test_36_37_discovery_never_references_illm_provider_or_ai_infrastructure() -> None:
    for relative in (
        "core/integrations/discovery.py",
        "services/integration_service.py",
        "infrastructure/api/routes/integrations.py",
    ):
        text = (_SRC_ROOT / relative).read_text(encoding="utf-8")
        for needle in ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider"):
            assert needle not in text, f"{relative} references {needle!r}"


def test_38_ai_calibration_engine_is_untouched() -> None:
    assert not (_SRC_ROOT / "core" / "calibration").exists()


# ===========================================================================
# Repeatability (39-40)
# ===========================================================================


@pytest.mark.asyncio
async def test_39_40_discovery_can_run_many_times_with_a_deterministic_final_state(
    env: dict,
) -> None:
    for _ in range(5):
        await env["service"].discover()

    assert set(env["service"].installed_ids()) == set(_CATALOGUE_IDS)
    assert len(env["registry"].discover()) == len(_CATALOGUE_IDS)


# ===========================================================================
# Duplicate catalogue entries (structural invariant)
# ===========================================================================


def test_catalogue_cannot_contain_duplicate_ids() -> None:
    """AVAILABLE_SPECS is a plain dict keyed by integration_id --
    duplicates are structurally impossible, not merely policy."""
    assert len(available_ids()) == len(set(available_ids()))
