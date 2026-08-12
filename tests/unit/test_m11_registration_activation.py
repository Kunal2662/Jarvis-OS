"""M11 Task Group D -- Runtime Registration & Activation tests.

TG-D's own analysis (``docs/M11_API_CENTER_LOGIC_CONTRACT.md`` §10)
found that the runtime lifecycle it describes -- Register, Activate,
Deactivate -- is already fully implemented by
``IntegrationService.install()`` / ``.connect()`` / ``.disconnect()``,
which already establish the exact runtime relationship (``IntegrationSpec``
-> ``MCPProviderRegistry`` entry -> credential-backed, locally-only
activation) the task group's objective describes, and are already REST-
reachable. No new service methods, registry, provider manager, or
credential store were introduced -- this file exists to *prove* the
objective is met, not to add a parallel mechanism.

No ``unittest.mock``, no HTTP-library patching. Real components
throughout, matching ``tests/unit/test_integration_provider.py`` and
``tests/unit/test_m11_health_surface.py``'s conventions.
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
        "provider_registry": provider_registry,
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


# ===========================================================================
# Registration (1-7)
# ===========================================================================


@pytest.mark.asyncio
async def test_1_register_a_valid_catalogue_backed_integration(env: dict) -> None:
    record = await env["service"].install(_GOOGLE_GMAIL)
    assert record["provider_id"] == _GOOGLE_GMAIL


@pytest.mark.asyncio
async def test_2_registration_creates_exactly_one_runtime_entry(env: dict) -> None:
    await env["service"].install(_GOOGLE_GMAIL)
    assert env["provider_registry"].discover() != ()
    matching = [r for r in env["provider_registry"].discover() if r.provider_id == _GOOGLE_GMAIL]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_3_duplicate_registration_is_deterministic_not_silently_duplicated(
    env: dict,
) -> None:
    """Existing, already-tested semantics (mirrors
    tests/unit/test_integrations_route.py::test_installing_twice_without_replace_is_a_400):
    a second install without ``replace=True`` is rejected, never
    silently creates a second entry."""
    await env["service"].install(_GOOGLE_GMAIL)

    with pytest.raises(ServiceError):
        await env["service"].install(_GOOGLE_GMAIL)

    matching = [r for r in env["provider_registry"].discover() if r.provider_id == _GOOGLE_GMAIL]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_4_and_5_unknown_integration_is_rejected(env: dict) -> None:
    """Also covers "missing local configuration": in this architecture,
    local-configuration validity for registration *is* catalogue/spec
    validity (``IntegrationSpec.validate()``, exhaustively covered by
    tests/unit/test_integration_catalogue.py and
    tests/unit/test_integration_models.py, not re-tested here) -- an id
    that fails to resolve to a valid spec is rejected the same way an
    unknown id is."""
    with pytest.raises(ServiceError):
        await env["service"].install("not_a_real_integration")


@pytest.mark.asyncio
async def test_6_missing_credential_reference_does_not_block_registration(env: dict) -> None:
    """Installing before a credential exists is the documented,
    intentional "approval screen" design (see ``install()``'s own
    docstring) -- registration must succeed, and the missing credential
    must be visible, not hidden or silently invented."""
    await env["service"].install(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["credential_configured"] is False
    assert health["credential_status"] == "missing"


# ===========================================================================
# Activation (8-14)
# ===========================================================================


@pytest.mark.asyncio
async def test_8_activate_a_registered_integration(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)

    status = await env["service"].connect(_GOOGLE_GMAIL)

    assert status["state"] == "connected"


@pytest.mark.asyncio
async def test_9_activation_changes_the_correct_local_runtime_state(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    before = env["provider_registry"].get(_GOOGLE_GMAIL)
    assert before is not None
    assert before.state.value == "initialized"

    await env["service"].connect(_GOOGLE_GMAIL)

    after = env["provider_registry"].get(_GOOGLE_GMAIL)
    assert after is not None
    assert after.state.value == "connected"


@pytest.mark.asyncio
async def test_10_activation_is_reflected_by_tg_c_health(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)

    assert health["healthy"] is True
    assert health["state"] == "connected"


@pytest.mark.asyncio
async def test_12_activation_without_registration_fails_correctly(env: dict) -> None:
    with pytest.raises(ServiceError):
        await env["service"].connect(_GOOGLE_GMAIL)


@pytest.mark.asyncio
async def test_13_activation_with_missing_credential_fails_and_never_reports_active(
    env: dict,
) -> None:
    """State consistency: a failed activation must never be reported as
    connected/active afterward (``MCPProviderManager._safe`` lands a
    failure in ``FAILED``, never leaves it looking connected)."""
    await env["service"].install(_GOOGLE_GMAIL)

    with pytest.raises(ServiceError):
        await env["service"].connect(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["healthy"] is False
    assert health["state"] != "connected"


@pytest.mark.asyncio
async def test_14_activation_does_not_expose_credentials(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL, access_token="super-secret-token")
    await env["service"].install(_GOOGLE_GMAIL)

    status = await env["service"].connect(_GOOGLE_GMAIL)

    assert "super-secret-token" not in repr(status)


# ===========================================================================
# Deactivation (15-19)
# ===========================================================================


@pytest.mark.asyncio
async def test_15_deactivate_an_active_integration(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    deactivated = await env["service"].disconnect(_GOOGLE_GMAIL)

    assert deactivated is True


@pytest.mark.asyncio
async def test_16_deactivation_updates_local_runtime_state(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    await env["service"].disconnect(_GOOGLE_GMAIL)

    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["state"] == "disconnected"
    assert health["healthy"] is False


@pytest.mark.asyncio
async def test_17_deactivation_preserves_stored_credentials(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    await env["service"].disconnect(_GOOGLE_GMAIL)

    assert env["store"].get(_GOOGLE_GMAIL) is not None
    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["credential_configured"] is True


@pytest.mark.asyncio
async def test_18_repeated_deactivation_is_deterministic(env: dict) -> None:
    _store_credential(env["store"], _GOOGLE_GMAIL)
    await env["service"].install(_GOOGLE_GMAIL)
    await env["service"].connect(_GOOGLE_GMAIL)

    first = await env["service"].disconnect(_GOOGLE_GMAIL)
    second = await env["service"].disconnect(_GOOGLE_GMAIL)

    assert first is True
    assert second is True
    health = await env["service"].health(_GOOGLE_GMAIL)
    assert health["state"] == "disconnected"


# ===========================================================================
# Network safety (7 / 11 / 19) -- would fail if a vendor request were made
# ===========================================================================


def _synthetic_spec(base_url: str) -> IntegrationSpec:
    return IntegrationSpec(
        integration_id="acme_lifecycle_probe",
        name="Acme Lifecycle Probe",
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
async def test_register_activate_deactivate_make_zero_vendor_requests(
    tmp_path: Path, vendor_server
) -> None:
    """Exercises the exact chain IntegrationService.install()/connect()/
    disconnect() use (MCPProviderManager -> RestIntegrationProvider)
    directly against a real local vendor stand-in, across the full
    register -> activate -> deactivate lifecycle. ``vendor_server.seen``
    staying empty is the proof."""
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
    spec = _synthetic_spec(str(vendor_server.make_url("")).rstrip("/"))
    provider = RestIntegrationProvider(spec, gateway=gateway, auth_manager=auth, account_id="me")

    try:
        await manager.install(
            spec.integration_id, spec.to_metadata(), provider=provider
        )  # register
        await manager.initialize(spec.integration_id)

        store.put(
            Credential(
                provider_id=spec.integration_id,
                method=AuthMethod.OAUTH2,
                access_token="at-1",
                refresh_token="rt-1",
            ),
            persist=False,
        )
        assert await manager.connect(spec.integration_id) is True  # activate
        assert await manager.disconnect(spec.integration_id) is True  # deactivate
    finally:
        await gateway.stop()

    assert vendor_server.seen == []


# ===========================================================================
# Infrastructure reuse (20-24)
# ===========================================================================


@pytest.mark.asyncio
async def test_20_and_21_registration_and_activation_use_the_existing_registry_and_manager(
    env: dict,
) -> None:
    await env["service"].install(_GOOGLE_GMAIL)

    assert env["service"]._providers is env["provider_manager"]
    assert env["provider_manager"].registry is env["provider_registry"]


@pytest.mark.asyncio
async def test_22_and_23_activation_uses_the_existing_credential_store_and_auth_manager(
    env: dict,
) -> None:
    assert env["service"]._auth is env["auth"]
    assert env["auth"]._store is env["store"]


def test_24_no_duplicate_registry_or_credential_manager_class_exists() -> None:
    """Reuses TG-A's exact forbidden-name scan, applied fresh for TG-D:
    no lifecycle work in this task group introduced a parallel
    abstraction."""
    import ast

    forbidden = (
        "M11ProviderManager",
        "IntegrationProviderManager",
        "M11CredentialStore",
        "VendorCredentialStore",
        "IntegrationCredentialStore",
        "IntegrationRegistry2",
        "VendorRegistry2",
    )
    hits: list[str] = []
    for py_file in _SRC_ROOT.rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name in forbidden:
                hits.append(f"{py_file}:{node.lineno} defines {node.name}")
    assert not hits, hits


# ===========================================================================
# AI boundary (25-27)
# ===========================================================================


def test_25_integration_service_still_never_references_illm_provider() -> None:
    text = (_SRC_ROOT / "services" / "integration_service.py").read_text(encoding="utf-8")
    for needle in ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider"):
        assert needle not in text


@pytest.mark.asyncio
async def test_27_llm_category_credentials_remain_under_m5(tmp_path: Path) -> None:
    from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition
    from jarvis.services.api_center_service import ApiCenterService

    settings = Settings(data_dir=tmp_path)
    m5 = ApiCenterService(settings)
    llm_api = m5.add_api(
        ApiDefinition(
            name="TG-D Regression OpenAI Key",
            provider="OpenAI",
            category=ApiCategory.LLM,
            auth_type=ApiAuthType.API_KEY,
            api_key="sk-tgd-test",
        )
    )
    assert m5.get(llm_api.id).category is ApiCategory.LLM
