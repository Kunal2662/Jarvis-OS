"""Diagnostics tests -- Milestone 10.5 Task Group E, deliverable 5.

Two properties are asserted throughout:

*Collects, never computes.* Every figure the aggregator reports is
compared against the subsystem that owns it, so a diagnostic can never
drift into being a second source of truth.

*Read-only.* Calling every method must leave connection state,
registrations and credentials exactly as they were -- a diagnostic that
changes what it observes is not a diagnostic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.diagnostics import MCPDiagnostics
from jarvis.core.mcp.negotiation import PROTOCOL_VERSION
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.sdk import register_provider
from jarvis.core.mcp.sdk.examples import (
    EXAMPLE_PROVIDER_ID,
    EXAMPLE_TRANSPORT_TYPE,
    build_example_transport,
    example_capability,
    example_capability_invoker,
    example_config,
    example_provider,
)
from jarvis.core.mcp.server import MCPServerRuntime
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel

_TOKEN = "tok_DIAGNOSTICS_SECRET"


class _Platform:
    """Every MCP subsystem, wired the way the DI container wires them."""

    def __init__(self, tmp_path: Path) -> None:
        self.bus = EventBus()
        self.permissions = PermissionModel(self.bus, store_path=tmp_path / "perm.json")
        self.server = MCPServerRuntime(permission_model=self.permissions, event_bus=self.bus)
        self.transports = TransportFactoryRegistry()
        self.transports.register(EXAMPLE_TRANSPORT_TYPE, build_example_transport)
        self.client = MCPClientRuntime(event_bus=self.bus)
        self.registry = MCPProviderRegistry()
        self.manager = MCPProviderManager(
            self.registry,
            client_runtime=self.client,
            transport_registry=self.transports,
            permission_model=self.permissions,
            event_bus=self.bus,
        )
        self.strategies = build_default_strategy_registry()
        self.auth = MCPAuthManager(
            CredentialStore(tmp_path / "creds.json"),
            self.strategies,
            self.permissions,
            event_bus=self.bus,
        )
        self.diagnostics = MCPDiagnostics(
            server=self.server,
            client=self.client,
            transports=self.transports,
            provider_manager=self.manager,
            auth_manager=self.auth,
            auth_strategies=self.strategies,
        )


@pytest.fixture
async def platform(tmp_path: Path) -> _Platform:
    platform = _Platform(tmp_path)
    await platform.server.expose(example_capability(), example_capability_invoker)
    await register_provider(
        platform.manager, EXAMPLE_PROVIDER_ID, example_provider(), example_config()
    )
    return platform


# --- Runtime ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runtime_reports_the_negotiated_protocol(platform: _Platform) -> None:
    runtime = await platform.diagnostics.runtime()

    assert runtime["protocol_version"] == PROTOCOL_VERSION
    assert PROTOCOL_VERSION in runtime["supported_protocol_versions"]


@pytest.mark.asyncio
async def test_runtime_counts_match_the_owning_subsystems(platform: _Platform) -> None:
    """Collected, not recomputed: if these ever disagree, the aggregator
    has grown its own idea of the truth."""
    runtime = await platform.diagnostics.runtime()

    assert runtime["server"]["capability_count"] == len(platform.server.capabilities)
    assert runtime["server"]["id"] == platform.server.server_id
    assert runtime["client"]["connection_count"] == len(platform.client.server_ids)


@pytest.mark.asyncio
async def test_heartbeat_absent_is_reported_as_not_running(platform: _Platform) -> None:
    """The monitor is optional, so 'no monitor' must read as stopped
    rather than crash or claim it is running."""
    assert (await platform.diagnostics.runtime())["heartbeat_running"] is False


# --- Focused inspections ---------------------------------------------------------


@pytest.mark.asyncio
async def test_capabilities_come_from_the_server_registry(platform: _Platform) -> None:
    assert platform.diagnostics.capabilities() == platform.server.capabilities.snapshot()


@pytest.mark.asyncio
async def test_transports_come_from_the_transport_registry(platform: _Platform) -> None:
    assert platform.diagnostics.transports() == platform.transports.describe_all()


@pytest.mark.asyncio
async def test_providers_come_from_the_provider_registry(platform: _Platform) -> None:
    assert platform.diagnostics.providers() == platform.registry.snapshot()


@pytest.mark.asyncio
async def test_auth_methods_report_unimplemented_flows_honestly(platform: _Platform) -> None:
    described = {entry["method"]: entry for entry in platform.diagnostics.auth_methods()}

    assert described["oauth2"]["supported"] is False
    assert described["bearer_token"]["supported"] is True


# --- inspect_provider ------------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_provider_joins_all_four_subsystems(platform: _Platform) -> None:
    """The value of this call is that it answers 'why will this provider
    not work' without four separate lookups."""
    payload = await platform.diagnostics.inspect_provider(EXAMPLE_PROVIDER_ID)

    assert payload is not None
    assert set(payload) == {"provider", "connection", "authentication", "health"}
    assert payload["provider"]["provider_id"] == EXAMPLE_PROVIDER_ID
    assert payload["connection"] is None  # registered, never connected
    assert payload["authentication"] is None  # no credential stored


@pytest.mark.asyncio
async def test_inspect_provider_returns_none_for_an_unknown_id(platform: _Platform) -> None:
    """``None`` rather than an exception, so a CLI reports it cleanly
    instead of showing a traceback for a typo."""
    assert await platform.diagnostics.inspect_provider("not-installed") is None


@pytest.mark.asyncio
async def test_inspect_provider_shows_the_live_connection(platform: _Platform) -> None:
    await platform.manager.connect(EXAMPLE_PROVIDER_ID)

    payload = await platform.diagnostics.inspect_provider(EXAMPLE_PROVIDER_ID)

    assert payload is not None
    assert payload["connection"]["server_id"] == EXAMPLE_PROVIDER_ID
    assert payload["connection"]["state"] == "connected"

    await platform.manager.disconnect(EXAMPLE_PROVIDER_ID)


@pytest.mark.asyncio
async def test_inspect_provider_includes_authentication_once_stored(
    platform: _Platform,
) -> None:
    await platform.auth.authenticate(
        EXAMPLE_PROVIDER_ID, AuthMethod.BEARER_TOKEN, {"token": _TOKEN}
    )

    payload = await platform.diagnostics.inspect_provider(EXAMPLE_PROVIDER_ID)

    assert payload is not None
    assert payload["authentication"]["authenticated"] is True


# --- inspect_capability ----------------------------------------------------------


@pytest.mark.asyncio
async def test_inspect_capability_reports_jarvis_own_declaration(platform: _Platform) -> None:
    payload = platform.diagnostics.inspect_capability(example_capability().name)

    assert payload is not None
    assert payload["exposed_by_jarvis"] is True
    assert payload["declaration"]["kind"] == "tool"
    assert payload["offered_by_peers"] == []


@pytest.mark.asyncio
async def test_peer_offers_appear_only_once_the_permission_is_granted(
    platform: _Platform,
) -> None:
    """One peer's capability list must never be mistaken for JARVIS's
    own -- they authorize different things -- and a peer capability only
    counts as *offered* once negotiation has actually accepted it.

    Before the grant the M9 permission bridge negotiates it away, which
    is precisely what the ``registry.permissions_pending`` warning
    predicts; the diagnostic must report the negotiated reality rather
    than the peer's wish list."""
    name = example_capability().name

    await platform.manager.connect(EXAMPLE_PROVIDER_ID)
    pending = platform.diagnostics.inspect_capability(name)

    assert pending is not None
    assert pending["exposed_by_jarvis"] is True  # ours, unaffected by the peer
    assert pending["offered_by_peers"] == []

    await platform.manager.disconnect(EXAMPLE_PROVIDER_ID)
    await platform.permissions.grant(f"mcp:{EXAMPLE_PROVIDER_ID}", "agent_tools")
    await platform.manager.connect(EXAMPLE_PROVIDER_ID)

    granted = platform.diagnostics.inspect_capability(name)

    assert granted is not None
    assert granted["offered_by_peers"] == [EXAMPLE_PROVIDER_ID]

    await platform.manager.disconnect(EXAMPLE_PROVIDER_ID)


@pytest.mark.asyncio
async def test_inspect_capability_returns_none_when_nobody_offers_it(
    platform: _Platform,
) -> None:
    assert platform.diagnostics.inspect_capability("nobody.offers.this") is None


# --- Whole-platform --------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_delegates_to_the_shared_validator(platform: _Platform) -> None:
    """The CLI, the REST layer and the SDK must all get the same answer,
    which they only do if there is one implementation."""
    payload = platform.diagnostics.validate()

    assert payload["ok"] is True
    assert {i["code"] for i in payload["issues"]} == {
        "registry.permissions_pending",
        "registry.auth_method_unsupported",
    }


@pytest.mark.asyncio
async def test_report_is_json_serializable(platform: _Platform) -> None:
    """It is served over REST and printed by the CLI, so anything that
    does not survive ``json.dumps`` is a defect here, not there."""
    payload = await platform.diagnostics.report()

    assert set(payload) == {
        "runtime",
        "capabilities",
        "transports",
        "connections",
        "providers",
        "authentication",
        "auth_methods",
        "provider_health",
        "auth_health",
        "validation",
    }
    json.dumps(payload)


@pytest.mark.asyncio
async def test_summary_counts_agree_with_the_full_report(platform: _Platform) -> None:
    summary = await platform.diagnostics.summary()
    report = await platform.diagnostics.report()

    assert summary["capabilities"] == len(report["capabilities"])
    assert summary["providers"] == len(report["providers"])
    assert summary["connections"] == len(report["connections"])
    assert summary["validation_errors"] == report["validation"]["error_count"]


# --- Security --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_diagnostic_output_contains_a_token(platform: _Platform) -> None:
    """Asserted against the raw serialized payload, not a parsed field:
    a leak through an unexpected key would slip past a field-by-field
    check."""
    await platform.auth.authenticate(
        EXAMPLE_PROVIDER_ID, AuthMethod.BEARER_TOKEN, {"token": _TOKEN}
    )

    raw = json.dumps(await platform.diagnostics.report())

    assert _TOKEN not in raw
    assert json.dumps(await platform.diagnostics.summary()).count(_TOKEN) == 0
    assert _TOKEN not in json.dumps(list(platform.diagnostics.auth()))


# --- Read-only -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_change_nothing_they_observe(platform: _Platform) -> None:
    """Every read, twice, with the state captured either side."""
    before = (
        platform.registry.snapshot(),
        platform.client.snapshot(),
        platform.server.capabilities.snapshot(),
        platform.auth.public_snapshot(),
    )

    for _ in range(2):
        await platform.diagnostics.runtime()
        await platform.diagnostics.report()
        await platform.diagnostics.summary()
        await platform.diagnostics.inspect_provider(EXAMPLE_PROVIDER_ID)
        platform.diagnostics.inspect_capability(example_capability().name)
        platform.diagnostics.validate()

    assert (
        platform.registry.snapshot(),
        platform.client.snapshot(),
        platform.server.capabilities.snapshot(),
        platform.auth.public_snapshot(),
    ) == before


@pytest.mark.asyncio
async def test_diagnostics_never_connects_a_registered_provider(
    platform: _Platform,
) -> None:
    """Inspecting a provider that has never connected must not connect
    it -- otherwise running the CLI would change the system it reports
    on."""
    await platform.diagnostics.report()
    await platform.diagnostics.inspect_provider(EXAMPLE_PROVIDER_ID)

    assert platform.client.server_ids == ()


@pytest.mark.asyncio
async def test_empty_platform_reports_without_error(tmp_path: Path) -> None:
    """Nothing registered, nothing exposed: the aggregator must produce
    a clean empty report rather than assume something exists."""
    diagnostics = _Platform(tmp_path).diagnostics

    summary = await diagnostics.summary()

    assert summary["providers"] == 0
    assert summary["capabilities"] == 0
    assert summary["validation_ok"] is True
