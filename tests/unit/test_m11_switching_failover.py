"""M11 Task Group E -- Vendor Runtime Switching & Failover tests.

The current catalogue contains exactly one vendor family (Google
Workspace), and no two real catalogue entries share an operation name
-- so a *real* cross-vendor switch/failover cannot be demonstrated
today (see docs/M11_API_CENTER_LOGIC_CONTRACT.md §5/§24, and the ADR's
own acknowledgement of this). Per this task group's explicit test
requirements, the mechanism itself is proven with two synthetic,
locally-hosted test integrations (matching the exact pattern already
established in test_m11_connection_testing.py / test_m11_registration_
activation.py's network-safety tests) -- not a fabricated production
vendor. Structural checks (registration, capability, AI boundary) use
the real Google Workspace catalogue entry where no network behavior is
needed, matching Task Group D's own precedent.

No ``unittest.mock``, no patched provider managers, no fake production
registries -- every check is either a real-component construction or a
real local ``aiohttp`` fake-vendor server.
"""

from __future__ import annotations

import asyncio
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
from jarvis.core.mcp.server import principal_for
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.integration_service import IntegrationService

_SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "jarvis"
_OPERATION = "status.get"


# ---------------------------------------------------------------------------
# Two synthetic, locally-hosted candidate integrations sharing one
# operation -- the mechanism under test, not a fabricated vendor.
# ---------------------------------------------------------------------------
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


def _spec(integration_id: str, base_url: str, *, capability: bool = True) -> IntegrationSpec:
    operations: tuple[OperationSpec, ...] = ()
    if capability:
        operations = (
            OperationSpec(
                name=_OPERATION,
                method="GET",
                path="/probe",
                category="read",
                permissions=("network",),
                scopes=("vendor.read",),
            ),
        )
    else:
        operations = (
            OperationSpec(
                name="other.get",
                method="GET",
                path="/other",
                category="read",
                permissions=("network",),
                scopes=("vendor.read",),
            ),
        )
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
        operations=operations,
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
            "auth": auth,
            "store": store,
            "registry": registry,
            "manager": manager,
            "primary_vendor": primary_vendor.vendor,
            "alternate_vendor": alternate_vendor.vendor,
        }
    finally:
        await gateway.stop()


# ===========================================================================
# Runtime Switching (1-15)
# ===========================================================================


@pytest.mark.asyncio
async def test_1_2_3_authorized_switch_succeeds_and_identifies_source_and_target(
    env: dict,
) -> None:
    _store_credential(env["store"], "acme_alternate")

    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert result["outcome"] == "success"
    assert result["from_integration_id"] == "acme_primary"
    assert result["to_integration_id"] == "acme_alternate"
    target_record = env["registry"].get("acme_alternate")
    assert target_record is not None
    assert target_record.state.value == "connected"


@pytest.mark.asyncio
async def test_4_previous_source_is_deactivated(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")

    await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    source_record = env["registry"].get("acme_primary")
    assert source_record is not None
    assert source_record.state.value == "disconnected"


@pytest.mark.asyncio
async def test_5_failed_target_activation_never_falsely_reports_active(env: dict) -> None:
    """No credential stored for the target -- activation must fail, and
    the target must never be reported connected."""
    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert result["outcome"] == "failure"
    target_record = env["registry"].get("acme_alternate")
    assert target_record is not None
    assert target_record.state.value != "connected"


@pytest.mark.asyncio
async def test_6_failed_switch_preserves_the_source(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")
    # No credential for the target -- switch must fail before touching the source.

    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert result["outcome"] == "failure"
    source_record = env["registry"].get("acme_primary")
    assert source_record is not None
    assert source_record.state.value == "connected"


@pytest.mark.asyncio
async def test_7_credentials_are_unchanged_by_a_switch(env: dict) -> None:
    _store_credential(env["store"], "acme_primary", access_token="primary-token")
    _store_credential(env["store"], "acme_alternate", access_token="alternate-token")
    await env["service"].connect("acme_primary")

    await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert env["store"].get("acme_primary").access_token == "primary-token"
    assert env["store"].get("acme_alternate").access_token == "alternate-token"


@pytest.mark.asyncio
async def test_9_10_unknown_or_unregistered_target_is_rejected(env: dict) -> None:
    """An unregistered *target* is a structured failure (matching
    Connection Test's own "every failure is a classified result, not
    an extra exception path" convention), not an exception -- only an
    unknown *source* raises (nothing to switch away from)."""
    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="not_installed"
    )

    assert result["outcome"] == "failure"
    assert result["error_code"] == "target_not_registered"


@pytest.mark.asyncio
async def test_unknown_source_raises(env: dict) -> None:
    with pytest.raises(ServiceError):
        await env["service"].switch(
            operation=_OPERATION,
            from_integration_id="not_installed",
            to_integration_id="acme_alternate",
        )


@pytest.mark.asyncio
async def test_11_target_without_a_valid_credential_is_not_eligible(env: dict) -> None:
    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert result["outcome"] == "failure"
    assert result["error_code"] == "target_not_eligible"


@pytest.mark.asyncio
async def test_12_target_missing_the_required_capability_is_rejected(
    tmp_path: Path, primary_vendor, alternate_vendor
) -> None:
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
        provider_manager=manager, auth_manager=auth, gateway=gateway, settings=settings
    )

    primary_spec = _spec("acme_primary", str(primary_vendor.make_url("")).rstrip("/"))
    # The alternate deliberately does NOT declare _OPERATION.
    incompatible_spec = _spec(
        "acme_incompatible", str(alternate_vendor.make_url("")).rstrip("/"), capability=False
    )
    primary = RestIntegrationProvider(primary_spec, gateway=gateway, auth_manager=auth)
    incompatible = RestIntegrationProvider(incompatible_spec, gateway=gateway, auth_manager=auth)

    try:
        for provider_id, spec, provider in (
            ("acme_primary", primary_spec, primary),
            ("acme_incompatible", incompatible_spec, incompatible),
        ):
            await manager.install(provider_id, spec.to_metadata(), provider=provider)
            await manager.initialize(provider_id)
            service._installed[provider_id] = provider
        _store_credential(store, "acme_incompatible")

        result = await service.switch(
            operation=_OPERATION,
            from_integration_id="acme_primary",
            to_integration_id="acme_incompatible",
        )
    finally:
        await gateway.stop()

    assert result["outcome"] == "failure"
    assert result["error_code"] == "unsupported_capability"


@pytest.mark.asyncio
async def test_14_concurrent_switches_to_different_targets_are_independently_correct(
    env: dict,
) -> None:
    """Two different switch requests, two different targets -- neither
    corrupts the other's outcome. There is no single "active per
    capability" slot to race over (see module docstring / Logic
    Contract §14): each switch only touches its own named provider."""
    _store_credential(env["store"], "acme_alternate")

    result_a, result_b = await asyncio.gather(
        env["service"].switch(
            operation=_OPERATION,
            from_integration_id="acme_primary",
            to_integration_id="acme_alternate",
        ),
        env["service"].switch(
            operation=_OPERATION,
            from_integration_id="acme_primary",
            to_integration_id="acme_alternate",
        ),
    )

    assert result_a["outcome"] == "success"
    assert result_b["outcome"] == "success"
    assert env["registry"].get("acme_alternate").state.value == "connected"


@pytest.mark.asyncio
async def test_15_repeated_same_target_switch_is_deterministic(env: dict) -> None:
    _store_credential(env["store"], "acme_alternate")

    first = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )
    second = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert first["outcome"] == "success"
    assert second["outcome"] == "success"
    assert env["registry"].get("acme_alternate").state.value == "connected"


# ===========================================================================
# Failover (16-28)
# ===========================================================================


@pytest.mark.asyncio
async def test_16_retryable_failure_recovers_via_an_eligible_alternate(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"

    result = await env["service"].invoke_with_failover(
        "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
    )

    assert result["integration_id"] == "acme_alternate"
    assert result["failed_over_from"] == "acme_primary"
    assert len(env["alternate_vendor"].requests_seen) == 1


@pytest.mark.asyncio
async def test_17_non_retryable_authentication_failure_does_not_fail_over(env: dict) -> None:
    """No credential at all is a local, non-retryable refusal
    (MCPAuthError via authorize_capability) -- never reaches the
    gateway, never becomes a GatewayError, so it cannot be classified
    retryable and never triggers failover."""
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_alternate")
    # acme_primary has no credential at all.

    with pytest.raises(ServiceError):
        await env["service"].invoke_with_failover(
            "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
        )

    assert env["alternate_vendor"].requests_seen == []


@pytest.mark.asyncio
async def test_18_no_eligible_alternate_returns_no_eligible_alternate(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")
    env["primary_vendor"].mode = "500"

    with pytest.raises(ServiceError, match="NO_ELIGIBLE_ALTERNATE"):
        await env["service"].invoke_with_failover("acme_primary", _OPERATION)

    history = env["service"].failover_history()
    assert history[0]["outcome"] == "no_candidate"


@pytest.mark.asyncio
async def test_19_candidate_must_already_be_registered(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")
    env["primary_vendor"].mode = "500"

    with pytest.raises(ServiceError, match="NO_ELIGIBLE_ALTERNATE"):
        await env["service"].invoke_with_failover(
            "acme_primary", _OPERATION, candidate_integration_id="never_installed"
        )


@pytest.mark.asyncio
async def test_20_candidate_must_support_the_required_capability(
    tmp_path: Path, primary_vendor, alternate_vendor
) -> None:
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
        provider_manager=manager, auth_manager=auth, gateway=gateway, settings=settings
    )
    primary_spec = _spec("acme_primary", str(primary_vendor.make_url("")).rstrip("/"))
    incompatible_spec = _spec(
        "acme_incompatible", str(alternate_vendor.make_url("")).rstrip("/"), capability=False
    )
    primary = RestIntegrationProvider(primary_spec, gateway=gateway, auth_manager=auth)
    incompatible = RestIntegrationProvider(incompatible_spec, gateway=gateway, auth_manager=auth)

    try:
        for provider_id, spec, provider in (
            ("acme_primary", primary_spec, primary),
            ("acme_incompatible", incompatible_spec, incompatible),
        ):
            await manager.install(provider_id, spec.to_metadata(), provider=provider)
            await manager.initialize(provider_id)
            service._installed[provider_id] = provider
            principal = principal_for(provider_id)
            permissions.declare(principal, ["network"])
            await permissions.grant(principal, "network")
        _store_credential(store, "acme_primary")
        _store_credential(store, "acme_incompatible")
        await service.connect("acme_primary")
        await service.connect("acme_incompatible")
        primary_vendor.vendor.mode = "500"

        with pytest.raises(ServiceError, match="NO_ELIGIBLE_ALTERNATE"):
            await service.invoke_with_failover(
                "acme_primary", _OPERATION, candidate_integration_id="acme_incompatible"
            )
    finally:
        await gateway.stop()


@pytest.mark.asyncio
async def test_21_22_failover_never_registers_or_discovers(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")
    env["primary_vendor"].mode = "500"
    before = set(env["service"].installed_ids())

    with pytest.raises(ServiceError):
        await env["service"].invoke_with_failover("acme_primary", _OPERATION)

    assert set(env["service"].installed_ids()) == before


@pytest.mark.asyncio
async def test_23_failover_never_modifies_credentials(env: dict) -> None:
    _store_credential(env["store"], "acme_primary", access_token="primary-token")
    _store_credential(env["store"], "acme_alternate", access_token="alternate-token")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"

    await env["service"].invoke_with_failover(
        "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
    )

    assert env["store"].get("acme_primary").access_token == "primary-token"
    assert env["store"].get("acme_alternate").access_token == "alternate-token"


@pytest.mark.asyncio
async def test_24_25_exactly_one_candidate_attempt_no_chaining(env: dict) -> None:
    """Structural loop prevention: only one candidate parameter exists,
    and a failing candidate is reported failed, never retried or
    chained to a third integration."""
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"
    env["alternate_vendor"].mode = "500"

    with pytest.raises(ServiceError):
        await env["service"].invoke_with_failover(
            "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
        )

    # Exactly one request to the candidate -- no retry-of-the-candidate.
    assert len(env["alternate_vendor"].requests_seen) == 1


@pytest.mark.asyncio
async def test_26_failed_alternate_does_not_become_active(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"
    env["alternate_vendor"].mode = "500"

    with pytest.raises(ServiceError):
        await env["service"].invoke_with_failover(
            "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
        )

    history = env["service"].failover_history()
    assert history[0]["outcome"] == "failed"


@pytest.mark.asyncio
async def test_27_original_integration_state_is_unaffected_by_a_failed_failover(
    env: dict,
) -> None:
    """Failover never mutates the failed integration's own lifecycle
    state -- it only tries a different provider for this one call."""
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")
    env["primary_vendor"].mode = "500"
    before = env["registry"].get("acme_primary").state

    with pytest.raises(ServiceError):
        await env["service"].invoke_with_failover("acme_primary", _OPERATION)

    assert env["registry"].get("acme_primary").state == before


@pytest.mark.asyncio
async def test_28_successful_failover_produces_correct_runtime_state(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"

    result = await env["service"].invoke_with_failover(
        "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
    )

    assert result["status_code"] == 200
    assert env["registry"].get("acme_alternate").state.value == "connected"
    # The failed primary is untouched -- still connected, not silently
    # torn down (failover does not deactivate anything).
    assert env["registry"].get("acme_primary").state.value == "connected"
    history = env["service"].failover_history()
    assert history[0]["outcome"] == "recovered"


# ===========================================================================
# Separation (29-32)
# ===========================================================================


@pytest.mark.asyncio
async def test_29_connection_test_failure_does_not_switch_providers(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    _store_credential(env["store"], "acme_alternate")
    await env["service"].connect("acme_primary")
    env["primary_vendor"].mode = "500"

    result = await env["service"].test_connection("acme_primary", operation=_OPERATION)

    assert result["outcome"] == "failure"
    # Nothing about the alternate changed -- it was never touched.
    assert env["alternate_vendor"].requests_seen == []
    assert env["registry"].get("acme_alternate").state.value == "initialized"


@pytest.mark.asyncio
async def test_30_health_read_never_switches_providers(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")
    await env["service"].connect("acme_primary")

    await env["service"].health("acme_primary")

    assert env["alternate_vendor"].requests_seen == []
    assert env["registry"].get("acme_alternate").state.value == "initialized"


def test_31_registration_does_not_trigger_failover(env: dict) -> None:
    """Installation already happened in the env fixture (install() +
    initialize() for both providers) -- assert no failover record
    exists purely from that."""
    assert env["service"].failover_history() == []


@pytest.mark.asyncio
async def test_32_activation_does_not_trigger_failover(env: dict) -> None:
    _store_credential(env["store"], "acme_primary")

    await env["service"].connect("acme_primary")

    assert env["service"].failover_history() == []


# ===========================================================================
# Security (33-37)
# ===========================================================================


@pytest.mark.asyncio
async def test_33_no_credentials_in_switch_results(env: dict) -> None:
    _store_credential(env["store"], "acme_alternate", access_token="switch-secret-token")

    result = await env["service"].switch(
        operation=_OPERATION, from_integration_id="acme_primary", to_integration_id="acme_alternate"
    )

    assert "switch-secret-token" not in repr(result)


@pytest.mark.asyncio
async def test_34_no_credentials_in_failover_events(env: dict) -> None:
    _store_credential(env["store"], "acme_primary", access_token="primary-secret")
    _store_credential(env["store"], "acme_alternate", access_token="alternate-secret")
    await env["service"].connect("acme_primary")
    await env["service"].connect("acme_alternate")
    env["primary_vendor"].mode = "500"

    captured = []
    from jarvis.core.events.events import IntegrationFailoverEvent

    async def _capture(event: object) -> None:
        captured.append(event)

    env["service"]._event_bus.subscribe(IntegrationFailoverEvent, _capture)

    await env["service"].invoke_with_failover(
        "acme_primary", _OPERATION, candidate_integration_id="acme_alternate"
    )

    assert len(captured) == 1
    assert "primary-secret" not in repr(captured[0])
    assert "alternate-secret" not in repr(captured[0])


def test_35_36_request_models_accept_no_url_or_provider_class() -> None:
    from jarvis.infrastructure.api.routes.integrations import SwitchRequest

    fields = set(SwitchRequest.model_fields)
    assert fields == {"operation", "from_integration_id", "to_integration_id"}
    assert "url" not in fields
    assert "provider_class" not in fields
    assert "module" not in fields


# ===========================================================================
# AI boundary (38-40)
# ===========================================================================


def test_38_39_no_illm_provider_or_model_failover_referenced() -> None:
    for relative in (
        "services/integration_service.py",
        "core/integrations/switching.py",
        "core/integrations/failover.py",
        "infrastructure/api/routes/integrations.py",
    ):
        text = (_SRC_ROOT / relative).read_text(encoding="utf-8")
        for needle in ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider"):
            assert needle not in text, f"{relative} references {needle!r}"


@pytest.mark.asyncio
async def test_40_ai_calibration_engine_is_untouched(tmp_path: Path) -> None:
    """No AI Calibration Engine module exists to import -- confirming
    this task group did not create one."""
    calibration_dir = _SRC_ROOT / "core" / "calibration"
    assert not calibration_dir.exists()
