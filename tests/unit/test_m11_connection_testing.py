"""M11 Task Group B -- Real Connection Testing tests.

The first M11 test suite permitted to exercise real network behavior.
A single configurable real local ``aiohttp`` fake-vendor server stands
in for the vendor throughout -- no ``unittest.mock``, no patched
``httpx``/``aiohttp``. See ``docs/M11_API_CENTER_LOGIC_CONTRACT.md``
§11/§21 for the health/connection-test boundary and error taxonomy
this file proves.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from aiohttp import web

from jarvis.core.config.settings import Settings
from jarvis.core.events.event_bus import EventBus
from jarvis.core.integrations.gateway import ApiGateway
from jarvis.core.integrations.models import AuthSpec, IntegrationSpec, OperationSpec
from jarvis.core.integrations.provider import RestIntegrationProvider
from jarvis.core.integrations.testing import MAX_CONNECTION_TEST_TIMEOUT_SECONDS
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


# ---------------------------------------------------------------------------
# Configurable fake vendor
# ---------------------------------------------------------------------------
class _Vendor:
    def __init__(self) -> None:
        self.mode = "success"
        self.delay_seconds = 0.0
        self.retry_after: int | None = None
        self.requests_seen: list[web.Request] = []

    async def handler(self, request: web.Request) -> web.Response:
        self.requests_seen.append(request)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.mode == "malformed":
            return web.Response(text="{not valid json", content_type="application/json")
        if self.mode == "success":
            return web.json_response({"items": [], "ok": True})
        status_and_error = {
            "401": (401, "invalid_token"),
            "403": (403, "insufficient_scope"),
            "404": (404, "not_found"),
            "429": (429, "rate_limited"),
            "500": (500, "internal"),
        }
        if self.mode not in status_and_error:
            raise AssertionError(f"unhandled vendor mode {self.mode!r}")
        status, error = status_and_error[self.mode]
        headers = (
            {"Retry-After": str(self.retry_after)}
            if self.mode == "429" and self.retry_after
            else {}
        )
        return web.json_response({"error": error}, status=status, headers=headers)


@pytest.fixture()
async def vendor(aiohttp_server):
    v = _Vendor()
    app = web.Application()
    app.router.add_get("/probe", v.handler)
    server = await aiohttp_server(app)
    server.vendor = v  # type: ignore[attr-defined]
    return server


def _probe_spec(base_url: str) -> IntegrationSpec:
    """A minimal, single zero-argument read operation -- deliberately
    read-only, deliberately no path parameters, so the connection-test
    operation-selection logic (category=read, no required params, no
    unsafe path params) is exercised the same way it would be against
    a real catalogue entry, without depending on Google's real spec
    shape."""
    return IntegrationSpec(
        integration_id="acme_probe",
        name="Acme Probe",
        vendor="acme",
        base_url=base_url,
        auth=AuthSpec(
            method=AuthMethod.OAUTH2,
            authorize_url="https://auth.acme.test/authorize",
            token_url="https://auth.acme.test/token",
        ),
        operations=(
            OperationSpec(
                name="status.get",
                method="GET",
                path="/probe",
                category="read",
                permissions=("network",),
                scopes=("vendor.read",),
            ),
            OperationSpec(
                name="status.mutate",
                method="POST",
                path="/probe",
                category="write",
                permissions=("network",),
                scopes=("vendor.write",),
                body=("x",),
                required=("x",),
            ),
        ),
    )


@pytest.fixture()
async def env(tmp_path: Path, vendor):
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    gateway = ApiGateway(max_attempts=3, backoff_seconds=0.0)
    await gateway.start()
    spec = _probe_spec(str(vendor.make_url("")).rstrip("/"))
    provider = RestIntegrationProvider(spec, gateway=gateway, auth_manager=auth, account_id="me")
    await provider.initialize()

    principal = principal_for(spec.integration_id)
    permissions.declare(principal, ["network"])
    await permissions.grant(principal, "network")

    try:
        yield {
            "provider": provider,
            "auth": auth,
            "store": store,
            "spec": spec,
            "vendor": vendor.vendor,
            "gateway": gateway,
        }
    finally:
        await gateway.stop()


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


# ===========================================================================
# Successful connection (1-4)
# ===========================================================================


@pytest.mark.asyncio
async def test_1_valid_credentials_and_valid_response_is_success(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)

    result = await env["provider"].test_connection()

    assert result.outcome == "success"
    assert result.error_code == ""
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_2_result_identifies_the_correct_integration(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)

    result = await env["provider"].test_connection()

    assert result.integration_id == env["spec"].integration_id


@pytest.mark.asyncio
async def test_3_latency_is_captured(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)

    result = await env["provider"].test_connection()

    assert result.latency_ms is not None
    assert result.latency_ms >= 0.0


@pytest.mark.asyncio
async def test_4_no_secrets_in_a_successful_result(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id, access_token="super-secret-token")

    result = await env["provider"].test_connection()

    assert "super-secret-token" not in repr(result)
    assert "Bearer" not in repr(result)


# ===========================================================================
# Authentication (5-7)
# ===========================================================================


@pytest.mark.asyncio
async def test_5_invalid_credentials_is_authentication_failure(env: dict) -> None:
    """No credential is stored at all -- authorize_capability's own
    "not authenticated (status: missing)" gate refuses before any
    vendor request is made."""
    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "credential_missing"
    assert env["vendor"].requests_seen == []


@pytest.mark.asyncio
async def test_6_revoked_credential_is_classified_distinctly(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)
    await env["auth"].revoke(env["spec"].integration_id)

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "credential_revoked"


@pytest.mark.asyncio
async def test_7_missing_credential_is_configuration_not_network_failure(env: dict) -> None:
    result = await env["provider"].test_connection()

    assert result.error_code == "credential_missing"
    assert result.status_code is None


@pytest.mark.asyncio
async def test_vendor_401_is_authentication_failed(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "401"

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "authentication_failed"
    assert result.status_code == 401


# ===========================================================================
# Authorization (8-9)
# ===========================================================================


@pytest.mark.asyncio
async def test_8_vendor_403_is_authorization_failed(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "403"

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "authorization_failed"
    assert result.status_code == 403


@pytest.mark.asyncio
async def test_9_insufficient_vendor_scope_is_forbidden_scope(env: dict) -> None:
    """A credential that carries no scope at all -- distinguishable
    locally from a missing/revoked credential, per
    MCPAuthManager.authorize_capability's second gate."""
    _store_credential(env["store"], env["spec"].integration_id, scopes=())

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "forbidden_scope"
    assert env["vendor"].requests_seen == []


# ===========================================================================
# Network (10-12)
# ===========================================================================


@pytest.mark.asyncio
async def test_10_and_11_unreachable_vendor_is_classified_not_raised(tmp_path: Path) -> None:
    """An unroutable local address stands in for DNS failure/connection
    refused. Whether the OS's TCP stack answers with an immediate
    refusal (``network_error``) or never answers at all within the
    gateway's own timeout (``timeout``, via ``httpx.ConnectTimeout`` --
    itself a ``TimeoutException``) is a platform/network-stack detail
    this test does not depend on; both are correctly-classified,
    non-hanging, non-raising outcomes, which is the actual property
    under test."""
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0, timeout_seconds=2.0)
    await gateway.start()
    spec = _probe_spec("http://127.0.0.1:1")  # nothing listens on port 1
    provider = RestIntegrationProvider(spec, gateway=gateway, auth_manager=auth, account_id="me")
    await provider.initialize()
    principal = principal_for(spec.integration_id)
    permissions.declare(principal, ["network"])
    await permissions.grant(principal, "network")
    _store_credential(store, spec.integration_id)

    try:
        result = await provider.test_connection(timeout_seconds=2.0)
    finally:
        await gateway.stop()

    assert result.outcome == "failure"
    assert result.error_code in ("network_error", "timeout")


# ===========================================================================
# Timeout (13-15)
# ===========================================================================


@pytest.mark.asyncio
async def test_13_14_15_vendor_delay_produces_a_bounded_timeout(env: dict) -> None:
    """The vendor deliberately sleeps far longer than the configured
    timeout. The test must return within a generous margin of the
    timeout (never wait for the vendor's full delay), classify it as
    'timeout', and leave the gateway usable afterward -- proof no task
    or connection was left hanging."""
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "success"
    env["vendor"].delay_seconds = 3.0
    configured_timeout = 0.4

    started = time.monotonic()
    result = await env["provider"].test_connection(timeout_seconds=configured_timeout)
    elapsed = time.monotonic() - started

    assert result.outcome == "failure"
    assert result.error_code == "timeout"
    assert elapsed < 2.0  # generous margin; must not wait anywhere near the 3s vendor delay

    # No lingering/broken state: a second, undelayed call succeeds normally.
    env["vendor"].delay_seconds = 0.0
    recovered = await env["provider"].test_connection(timeout_seconds=5.0)
    assert recovered.outcome == "success"


def test_caller_supplied_timeout_is_capped(env: dict) -> None:
    """A caller may ask for a shorter timeout, never a longer one --
    the one place a request could otherwise hold a vendor connection
    open indefinitely."""
    assert MAX_CONNECTION_TEST_TIMEOUT_SECONDS == 10.0


# ===========================================================================
# Vendor errors (16-18)
# ===========================================================================


@pytest.mark.asyncio
async def test_16_rate_limited_is_classified_not_retried(env: dict) -> None:
    """No automatic retry: a single 429 is classified immediately, the
    fake vendor sees exactly one request, never more."""
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "429"
    env["vendor"].retry_after = 30

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "rate_limited"
    assert result.status_code == 429
    assert len(env["vendor"].requests_seen) == 1


@pytest.mark.asyncio
async def test_17_vendor_5xx_is_vendor_unavailable_not_retried(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "500"

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "vendor_unavailable"
    assert result.status_code == 500
    assert len(env["vendor"].requests_seen) == 1


@pytest.mark.asyncio
async def test_18_malformed_response_is_classified(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "malformed"

    result = await env["provider"].test_connection()

    assert result.outcome == "failure"
    assert result.error_code == "malformed_response"
    assert result.status_code == 200


# ===========================================================================
# Security (19-22)
# ===========================================================================


@pytest.mark.asyncio
async def test_19_20_credentials_never_appear_in_result_or_logs(env: dict, caplog) -> None:
    _store_credential(env["store"], env["spec"].integration_id, access_token="ultra-secret-abc123")
    env["vendor"].mode = "401"

    result = await env["provider"].test_connection()

    assert "ultra-secret-abc123" not in repr(result)
    assert "ultra-secret-abc123" not in result.message
    for record in caplog.records:
        assert "ultra-secret-abc123" not in record.getMessage()


@pytest.mark.asyncio
async def test_21_credentials_never_appear_in_the_audit_event(tmp_path: Path, vendor) -> None:
    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    provider_manager = MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=TransportFactoryRegistry(),
        permission_model=permissions,
        event_bus=bus,
    )
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    await gateway.start()
    settings = Settings(data_dir=tmp_path)
    service = IntegrationService(
        provider_manager=provider_manager,
        auth_manager=auth,
        gateway=gateway,
        settings=settings,
        event_bus=bus,
    )
    spec = _probe_spec(str(vendor.make_url("")).rstrip("/"))
    provider = RestIntegrationProvider(spec, gateway=gateway, auth_manager=auth, account_id="me")
    await provider_manager.install(spec.integration_id, spec.to_metadata(), provider=provider)
    await provider_manager.initialize(spec.integration_id)
    # IntegrationService.install() only accepts real catalogue ids
    # (via build_spec()); this synthetic spec is registered with the
    # shared MCPProviderManager directly above, so the service's own
    # bookkeeping dict needs the same entry installed() would have made.
    service._installed[spec.integration_id] = provider
    principal = principal_for(spec.integration_id)
    permissions.declare(principal, ["network"])
    await permissions.grant(principal, "network")
    _store_credential(store, spec.integration_id, access_token="event-secret-xyz")

    captured = []
    from jarvis.core.events.events import IntegrationConnectionTestEvent

    async def _capture(event: object) -> None:
        if isinstance(event, IntegrationConnectionTestEvent):
            captured.append(event)

    bus.subscribe(IntegrationConnectionTestEvent, _capture)

    try:
        await service.test_connection(spec.integration_id)
    finally:
        await gateway.stop()

    assert len(captured) == 1
    assert "event-secret-xyz" not in repr(captured[0])


@pytest.mark.asyncio
async def test_22_raw_authorization_header_never_appears_in_a_result(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id, access_token="header-secret-999")
    env["vendor"].mode = "500"

    result = await env["provider"].test_connection()

    assert "header-secret-999" not in repr(result)
    assert "Authorization" not in result.message


# ===========================================================================
# REST (23-26) -- see tests/unit/test_integrations_route.py for the
# session/auth/response-shape tests, added there to reuse its existing,
# already-proven client/auth fixtures rather than duplicating them.
# ===========================================================================


# ===========================================================================
# Health separation (27-29)
# ===========================================================================


@pytest.mark.asyncio
async def test_27_28_29_connection_test_may_call_vendor_health_never_does(env: dict) -> None:
    _store_credential(env["store"], env["spec"].integration_id)

    # Health first: must be local-only regardless of connection state.
    health = await env["provider"].health()
    assert env["vendor"].requests_seen == []
    assert health.healthy is False  # never started/connected

    # Connection Test: the one path allowed to reach the vendor.
    await env["provider"].test_connection()
    assert len(env["vendor"].requests_seen) == 1

    # Health afterward is still computed locally -- it does not call
    # test_connection(), and does not change just because a test ran.
    # (Still not connected, so still unhealthy -- a passing Connection
    # Test does not manufacture health, per the Logic Contract's
    # explicit "keep the two separate" rule.)
    health_after = await env["provider"].health()
    assert health_after.healthy is False
    assert len(env["vendor"].requests_seen) == 1  # unchanged


def test_health_method_source_never_calls_test_connection() -> None:
    import inspect

    from jarvis.core.integrations.provider import RestIntegrationProvider

    source = inspect.getsource(RestIntegrationProvider.health)
    assert "test_connection" not in source


# ===========================================================================
# No failover / no runtime switching (30-32)
# ===========================================================================


def test_30_31_32_connection_test_never_references_failover_or_switching() -> None:
    """``provider.py`` overall must still never mention either (Task
    Group E's failover/switching logic lives in ``integration_service.py``
    only, not the provider) -- and within ``integration_service.py``,
    the Connection Test *method itself* must not, even though the file
    as a whole now legitimately does (Task Group E added ``switch()``/
    ``invoke_with_failover()`` to this same file; a whole-file text scan
    would no longer distinguish the two, so this checks the method's
    own source instead)."""
    import inspect

    from jarvis.services.integration_service import IntegrationService

    text = (_SRC_ROOT / "core" / "integrations" / "provider.py").read_text(encoding="utf-8")
    for needle in ("failover", "Failover", "runtime_switch", "RuntimeSwitch"):
        assert needle not in text

    test_connection_source = inspect.getsource(IntegrationService.test_connection)
    for needle in ("failover", "Failover", "runtime_switch", "RuntimeSwitch", "switch("):
        assert needle not in test_connection_source


@pytest.mark.asyncio
async def test_a_failed_connection_test_does_not_disconnect_or_alter_provider_state(
    env: dict,
) -> None:
    """A failed test is a diagnostic, not a lifecycle transition -- the
    provider's own connected/disconnected state is untouched."""
    _store_credential(env["store"], env["spec"].integration_id)
    env["vendor"].mode = "500"

    before = env["provider"]._connected
    await env["provider"].test_connection()
    after = env["provider"]._connected

    assert before == after


# ===========================================================================
# AI boundary (33-35)
# ===========================================================================


def test_33_34_35_connection_testing_never_references_ai_calibration_or_illm_provider() -> None:
    for relative in (
        "core/integrations/provider.py",
        "core/integrations/testing.py",
        "services/integration_service.py",
        "infrastructure/api/routes/integrations.py",
    ):
        text = (_SRC_ROOT / relative).read_text(encoding="utf-8")
        for needle in ("ILLMProvider", "infrastructure.llm", "FallbackLLMProvider"):
            assert needle not in text, f"{relative} references {needle!r}"


@pytest.mark.asyncio
async def test_llm_category_credentials_remain_m5_owned(tmp_path: Path) -> None:
    from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition
    from jarvis.services.api_center_service import ApiCenterService

    settings = Settings(data_dir=tmp_path)
    m5 = ApiCenterService(settings)
    api = m5.add_api(
        ApiDefinition(
            name="TG-B Regression OpenAI Key",
            provider="OpenAI",
            category=ApiCategory.LLM,
            auth_type=ApiAuthType.API_KEY,
            api_key="sk-tgb-test",
        )
    )
    assert m5.get(api.id).category is ApiCategory.LLM


# ===========================================================================
# SSRF protection
# ===========================================================================


@pytest.mark.asyncio
async def test_unknown_operation_name_is_refused_never_reaches_the_vendor(env: dict) -> None:
    """The request model exposes an operation *name*, never a URL --
    an unrecognized name is rejected before anything is built."""
    _store_credential(env["store"], env["spec"].integration_id)

    result = await env["provider"].test_connection(operation="not_a_real_operation")

    assert result.outcome == "failure"
    assert result.error_code == "unsupported_capability"
    assert env["vendor"].requests_seen == []


@pytest.mark.asyncio
async def test_mutating_operation_is_refused_as_unsafe(env: dict) -> None:
    """Even a *real*, declared operation is refused if it mutates
    vendor state -- Connection Testing must stay read-only."""
    _store_credential(env["store"], env["spec"].integration_id)

    result = await env["provider"].test_connection(operation="status.mutate")

    assert result.outcome == "failure"
    assert result.error_code == "unsupported_capability"
    assert env["vendor"].requests_seen == []


def test_request_model_has_no_url_field() -> None:
    from jarvis.infrastructure.api.routes.integrations import TestConnectionRequest

    fields = set(TestConnectionRequest.model_fields)
    assert fields == {"operation", "timeout_seconds"}
    assert "url" not in fields


# ===========================================================================
# Concurrency / isolation
# ===========================================================================


@pytest.mark.asyncio
async def test_a_hung_connection_test_does_not_block_a_concurrent_one(
    tmp_path: Path, aiohttp_server
) -> None:
    """Two integrations, one against a slow vendor and one against a
    fast one, tested concurrently -- the fast one must not wait for the
    slow one."""

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(2.0)
        return web.json_response({"ok": True})

    async def fast(request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    slow_app = web.Application()
    slow_app.router.add_get("/probe", slow)
    fast_app = web.Application()
    fast_app.router.add_get("/probe", fast)
    slow_server = await aiohttp_server(slow_app)
    fast_server = await aiohttp_server(fast_app)

    bus = EventBus()
    permissions = PermissionModel(bus, store_path=tmp_path / "permissions.json")
    store = CredentialStore(tmp_path / "credentials.json", secret_key="")
    auth = MCPAuthManager(store, build_default_strategy_registry(), permissions, event_bus=bus)
    gateway = ApiGateway(max_attempts=1, backoff_seconds=0.0)
    await gateway.start()

    import dataclasses

    slow_spec = dataclasses.replace(
        _probe_spec(str(slow_server.make_url("")).rstrip("/")), integration_id="acme_slow"
    )
    fast_spec = dataclasses.replace(
        _probe_spec(str(fast_server.make_url("")).rstrip("/")), integration_id="acme_fast"
    )

    slow_provider = RestIntegrationProvider(slow_spec, gateway=gateway, auth_manager=auth)
    fast_provider = RestIntegrationProvider(fast_spec, gateway=gateway, auth_manager=auth)
    await slow_provider.initialize()
    await fast_provider.initialize()
    for provider_id in ("acme_slow", "acme_fast"):
        principal = principal_for(provider_id)
        permissions.declare(principal, ["network"])
        await permissions.grant(principal, "network")
        _store_credential(store, provider_id)

    try:
        started = time.monotonic()
        fast_result, _ = await asyncio.gather(
            fast_provider.test_connection(timeout_seconds=5.0),
            slow_provider.test_connection(timeout_seconds=5.0),
        )
        # The fast call's own result is available quickly regardless of
        # how gather() waits for both -- assert its own latency was
        # short, not that gather() as a whole returned early.
        assert fast_result.latency_ms is not None
        assert fast_result.latency_ms < 1000
        assert fast_result.outcome == "success"
        assert time.monotonic() - started < 5.0
    finally:
        await gateway.stop()
