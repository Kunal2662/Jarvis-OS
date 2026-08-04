"""MCP SDK end-to-end -- Milestone 10.5 Task Group E, deliverable 7.

Walks the whole author journey once, against the **real** DI container,
the real runtime and the real REST app:

    build a capability -> build a provider -> expose -> register ->
    grant -> connect -> authenticate -> inspect from the CLI -> inspect
    from REST

The unit tests prove each piece works; this proves the pieces are the
*same* pieces. In particular it asserts that the CLI and the REST API --
two independent delivery mechanisms -- report identical facts. If they
ever diverge, one of them has grown its own copy of the runtime.

Same single-``asyncio.run``-per-scenario discipline the other MCP
integration tests use, for the same reason: transports are bound to the
loop that created them.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

_PROVIDER_ID = "e2e"
_TOKEN = "tok_E2E_SECRET_VALUE"


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}


def _sdk_objects():
    """One capability, provider and config, all built only through the
    public SDK surface -- which is the actual claim deliverable 1
    makes."""
    from jarvis.core.mcp.sdk import (
        CapabilityBuilder,
        ConfigBuilder,
        ProviderBuilder,
        TransportBuilder,
    )
    from jarvis.core.mcp.sdk.examples import EXAMPLE_TRANSPORT_TYPE

    capability = (
        CapabilityBuilder("e2e.echo")
        .describe("Echoes text back.")
        .with_permission("agent_tools")
        .build()
    )
    metadata = (
        ProviderBuilder("E2E Provider")
        .describe("Built entirely through the SDK.")
        .transport(EXAMPLE_TRANSPORT_TYPE)
        .with_capability(capability)
        .with_permission("agent_tools")
        .build()
    )
    config = (
        ConfigBuilder()
        .from_transport(TransportBuilder(EXAMPLE_TRANSPORT_TYPE).option("client_id", "e2e"))
        .build(metadata)
    )
    return capability, metadata, config


def test_author_journey_from_sdk_to_connected_provider(client) -> None:
    """The whole path, through the container's own singletons."""
    from jarvis.core.mcp.providers.metadata import ProviderState
    from jarvis.core.mcp.sdk import expose_capabilities, register_provider
    from jarvis.core.mcp.sdk.examples import (
        EXAMPLE_TRANSPORT_TYPE,
        build_example_transport,
        example_capability_invoker,
    )

    container = client.container
    server = container.mcp_server_runtime()
    manager = container.mcp_provider_manager()
    permissions = container.permission_model()
    diagnostics = container.mcp_diagnostics()
    capability, metadata, config = _sdk_objects()

    async def scenario() -> None:
        # The shipped in-process transport dispatches to JARVIS's own
        # server runtime; the example factory stands in for a peer.
        container.mcp_transport_registry().register(EXAMPLE_TRANSPORT_TYPE, build_example_transport)

        assert await expose_capabilities(server, [capability]) == ("e2e.echo",)
        await server.expose(capability, example_capability_invoker, replace=True)
        await register_provider(manager, _PROVIDER_ID, metadata, config)

        # Installing declares the scope; it never grants it.
        assert ("mcp:e2e", "agent_tools") in permissions.pending()
        assert "registry.permissions_pending" in {
            issue["code"] for issue in diagnostics.validate()["issues"]
        }

        await permissions.grant("mcp:e2e", "agent_tools")
        assert await manager.connect(_PROVIDER_ID) is True
        assert manager.registry.require(_PROVIDER_ID).state is ProviderState.CONNECTED

        payload = await diagnostics.inspect_provider(_PROVIDER_ID)
        assert payload is not None
        assert payload["connection"]["state"] == "connected"
        assert payload["health"]["healthy"] is True

        # ``metadata.capabilities`` is advisory; the authoritative list
        # is whatever negotiation accepted. The example peer offers
        # ``example.echo`` regardless of what the provider declared, and
        # the diagnostic reports that reality rather than the wish list.
        assert metadata.capabilities == ("e2e.echo",)
        assert payload["connection"]["capabilities"] == ["example.echo"]
        assert diagnostics.inspect_capability("example.echo")["offered_by_peers"] == [_PROVIDER_ID]
        assert diagnostics.inspect_capability("e2e.echo")["offered_by_peers"] == []

        await manager.disconnect(_PROVIDER_ID)

    asyncio.run(scenario())


def test_cli_and_rest_report_the_same_platform(client, auth_headers) -> None:
    """Two delivery mechanisms, one runtime."""
    from jarvis.core.mcp.sdk import expose_capabilities, register_provider
    from jarvis.infrastructure.cli.mcp_cli import run_command

    container = client.container
    server = container.mcp_server_runtime()
    manager = container.mcp_provider_manager()
    diagnostics = container.mcp_diagnostics()
    capability, metadata, config = _sdk_objects()

    async def scenario() -> None:
        await expose_capabilities(server, [capability])
        await register_provider(manager, _PROVIDER_ID, metadata, config)

        rest_providers = (
            await asyncio.to_thread(client.get, "/api/v1/mcp/providers", headers=auth_headers)
        ).json()["data"]
        rest_capabilities = (
            await asyncio.to_thread(client.get, "/api/v1/mcp/capabilities", headers=auth_headers)
        ).json()["data"]

        cli_providers, provider_code = await run_command(diagnostics, "providers", as_json=True)
        cli_capabilities, capability_code = await run_command(
            diagnostics, "capabilities", as_json=True
        )

        assert (provider_code, capability_code) == (0, 0)
        assert [p["provider_id"] for p in json.loads(cli_providers)] == [
            p["provider_id"] for p in rest_providers
        ]
        assert [c["name"] for c in json.loads(cli_capabilities)] == [
            c["name"] for c in rest_capabilities
        ]

    asyncio.run(scenario())


def test_credentials_never_reach_any_surface(client, auth_headers) -> None:
    """The one property worth re-proving at integration level: a token
    stored through the auth manager must not appear in the diagnostics
    report, the CLI's output, or the REST response -- asserted against
    raw text, so a leak through an unexpected key cannot slip past."""
    from jarvis.core.mcp.auth.credentials import AuthMethod
    from jarvis.infrastructure.cli.mcp_cli import run_command

    container = client.container
    auth = container.mcp_auth_manager()
    diagnostics = container.mcp_diagnostics()

    async def scenario() -> None:
        await auth.authenticate(_PROVIDER_ID, AuthMethod.BEARER_TOKEN, {"token": _TOKEN})

        report = json.dumps(await diagnostics.report())
        cli_output, _ = await run_command(diagnostics, "auth", as_json=True)
        rest = await asyncio.to_thread(client.get, "/api/v1/mcp/auth", headers=auth_headers)

        assert _TOKEN not in report
        assert _TOKEN not in cli_output
        assert _TOKEN not in rest.text
        # ...and the credential is still usable in memory, so the
        # absence above is redaction rather than data loss.
        assert auth.status(_PROVIDER_ID)["authenticated"] is True

    asyncio.run(scenario())


def test_rest_diagnostics_matches_the_cli(client, auth_headers) -> None:
    """``GET /mcp/diagnostics`` and ``jarvis mcp list --json`` are two
    renderings of one aggregate, so their content must be identical."""
    from jarvis.core.mcp.sdk import expose_capabilities, register_provider
    from jarvis.infrastructure.cli.mcp_cli import run_command

    container = client.container
    server = container.mcp_server_runtime()
    manager = container.mcp_provider_manager()
    diagnostics = container.mcp_diagnostics()
    capability, metadata, config = _sdk_objects()

    async def scenario() -> None:
        await expose_capabilities(server, [capability])
        await register_provider(manager, _PROVIDER_ID, metadata, config)

        response = await asyncio.to_thread(
            client.get, "/api/v1/mcp/diagnostics", headers=auth_headers
        )
        cli_output, _ = await run_command(diagnostics, "list", as_json=True)

        assert response.status_code == 200
        body = response.json()
        assert body["data"] == json.loads(cli_output)
        assert body["meta"]["providers"] == 1

    asyncio.run(scenario())


def test_rest_validate_reports_findings_without_failing(client, auth_headers) -> None:
    """A configuration problem is a finding, not a broken endpoint --
    callers branch on ``data.ok`` rather than on the status code."""
    from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata

    manager = client.container.mcp_provider_manager()

    async def scenario() -> None:
        clean = await asyncio.to_thread(client.get, "/api/v1/mcp/validate", headers=auth_headers)
        assert clean.status_code == 200
        assert clean.json()["data"]["ok"] is True

        # A transport this build never registered: the provider is
        # valid, the pairing is not.
        client.container.mcp_transport_registry().unregister("websocket")
        await manager.install(
            "broken",
            ProviderMetadata(name="Broken", description="d", transport="websocket"),
            ProviderConfig(transport="websocket", options={"url": "ws://localhost:1"}),
        )

        broken = await asyncio.to_thread(client.get, "/api/v1/mcp/validate", headers=auth_headers)

        assert broken.status_code == 200
        assert broken.json()["data"]["ok"] is False
        assert broken.json()["meta"]["error_count"] == 1
        assert "registry.transport_not_registered" in {
            issue["code"] for issue in broken.json()["data"]["issues"]
        }

    asyncio.run(scenario())


def test_di_container_exposes_one_diagnostics_singleton(client) -> None:
    """Resolved twice it must be the same object -- otherwise the CLI
    and the API would be inspecting different runtimes."""
    from jarvis.core.mcp.diagnostics import MCPDiagnostics

    container = client.container

    first = container.mcp_diagnostics()
    second = container.mcp_diagnostics()

    assert first is second
    assert isinstance(first, MCPDiagnostics)


def test_di_diagnostics_reads_the_containers_own_runtime(client) -> None:
    """Wired to the same singletons the REST routes resolve, not to
    fresh instances of its own."""
    container = client.container
    diagnostics = container.mcp_diagnostics()

    assert diagnostics.capabilities() == container.mcp_server_runtime().capabilities.snapshot()
    assert diagnostics.transports() == container.mcp_transport_registry().describe_all()
    assert diagnostics.providers() == container.mcp_provider_manager().registry.snapshot()
    assert diagnostics.auth_methods() == container.mcp_auth_strategies().describe()


def test_run_mcp_cli_uses_the_containers_diagnostics_singleton(client, capsys) -> None:
    """The CLI must resolve the shared singleton, not assemble its own
    aggregator -- otherwise ``jarvis mcp`` and the REST API could
    disagree."""
    from jarvis.infrastructure.cli.mcp_cli import run_mcp_cli

    exit_code = run_mcp_cli(["status", "--json"], container=client.container)
    printed = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert printed == asyncio.run(client.container.mcp_diagnostics().summary())


def test_jarvis_mcp_dispatches_before_the_application_parser() -> None:
    """``jarvis mcp ...`` must never fall through to the run-mode
    parser, or a developer inspecting an install would launch it."""
    import jarvis.infrastructure.cli.mcp_cli as cli_module
    import jarvis.main as main_module

    called: dict[str, object] = {}

    def _fake_cli(argv, **kwargs) -> int:
        called["argv"] = list(argv)
        return 0

    original = cli_module.run_mcp_cli
    cli_module.run_mcp_cli = _fake_cli  # type: ignore[assignment]
    try:
        assert main_module.main(["mcp", "status", "--json"]) == 0
    finally:
        cli_module.run_mcp_cli = original  # type: ignore[assignment]

    assert called["argv"] == ["status", "--json"]
