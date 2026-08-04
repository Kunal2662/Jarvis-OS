"""``jarvis mcp`` CLI tests -- Milestone 10.5 Task Group E,
deliverable 2.

``run_command`` returns ``(output, exit_code)`` instead of printing, so
these assert on values rather than captured stdout -- a test that
scrapes stdout tends to pass for the wrong reason.

Every command runs against a real ``MCPDiagnostics`` over the real
runtime. A faked aggregator would only prove the renderer works on
invented shapes.
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
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata
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
from jarvis.infrastructure.cli.mcp_cli import (
    _COMMANDS,
    _render_table,
    build_mcp_parser,
    run_command,
)

_TOKEN = "tok_CLI_SECRET"


class _Platform:
    """The subsystems behind the CLI, kept addressable so a test can
    change the world the CLI reports on without reaching into the
    aggregator's privates."""

    def __init__(self, tmp_path: Path) -> None:
        self.bus = EventBus()
        self.permissions = PermissionModel(self.bus, store_path=tmp_path / "perm.json")
        self.server = MCPServerRuntime(permission_model=self.permissions, event_bus=self.bus)
        self.transports = TransportFactoryRegistry()
        self.transports.register(EXAMPLE_TRANSPORT_TYPE, build_example_transport)
        self.client = MCPClientRuntime(event_bus=self.bus)
        self.manager = MCPProviderManager(
            MCPProviderRegistry(),
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


@pytest.fixture
def diagnostics(platform: _Platform) -> MCPDiagnostics:
    return platform.diagnostics


# --- Parser ----------------------------------------------------------------------


def test_parser_accepts_every_declared_command() -> None:
    parser = build_mcp_parser()

    for command in _COMMANDS:
        assert parser.parse_args([command]).command == command


def test_parser_rejects_an_unknown_command() -> None:
    """argparse exits rather than raising, which is the right shell
    behaviour -- asserted so a future refactor cannot silently accept
    anything."""
    with pytest.raises(SystemExit):
        build_mcp_parser().parse_args(["deploy"])


def test_parser_exposes_target_and_json_flag() -> None:
    args = build_mcp_parser().parse_args(["inspect", "demo", "--json"])

    assert (args.command, args.target, args.as_json) == ("inspect", "demo", True)
    assert args.config is None


def test_parser_accepts_an_alternate_env_file() -> None:
    """Matches ``jarvis --config``: a developer inspecting a non-default
    install must be able to point at the same .env the app would use."""
    args = build_mcp_parser().parse_args(["status", "--config", "other.env"])

    assert args.config == "other.env"


def test_no_vendor_specific_commands_exist() -> None:
    """The task group forbids them: the CLI describes the *platform*, and
    a provider appears only because it was registered."""
    vendors = {"github", "gmail", "slack", "discord", "notion", "drive", "dropbox", "outlook"}

    assert not vendors & set(_COMMANDS)


# --- Rendering -------------------------------------------------------------------


def test_render_table_aligns_and_labels_columns() -> None:
    output = _render_table([{"a": 1, "b": "x"}], ["a", "b"])
    lines = output.splitlines()

    assert lines[0].split() == ["a", "b"]
    assert set(lines[1]) == {"-", " "}
    assert lines[2].split() == ["1", "x"]


def test_render_table_says_none_rather_than_printing_a_bare_header() -> None:
    assert _render_table([], ["a"]) == "(none)"


def test_render_table_formats_scalars_readably() -> None:
    output = _render_table([{"a": True, "b": None, "c": ["x", "y"]}], ["a", "b", "c"])

    assert "yes" in output
    assert "-" in output
    assert "x, y" in output


def test_underscored_column_names_are_humanised() -> None:
    assert "provider id" in _render_table([{"provider_id": "demo"}], ["provider_id"])


# --- Commands --------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("command", _COMMANDS)
async def test_every_command_succeeds_against_a_real_runtime(
    diagnostics: MCPDiagnostics, command: str
) -> None:
    """``inspect`` needs a target; everything else must work bare."""
    target = EXAMPLE_PROVIDER_ID if command == "inspect" else ""

    output, code = await run_command(diagnostics, command, target)

    assert code == 0
    assert output


@pytest.mark.asyncio
@pytest.mark.parametrize("command", _COMMANDS)
async def test_json_output_is_parseable_for_every_command(
    diagnostics: MCPDiagnostics, command: str
) -> None:
    """``--json`` exists so another tool can consume it; output that
    only looks like JSON would be worse than none."""
    target = EXAMPLE_PROVIDER_ID if command == "inspect" else ""

    output, _ = await run_command(diagnostics, command, target, as_json=True)

    json.loads(output)


@pytest.mark.asyncio
async def test_status_reports_the_platform_counts(diagnostics: MCPDiagnostics) -> None:
    output, code = await run_command(diagnostics, "status")

    assert code == 0
    assert "capabilities: 1" in output
    assert "providers: 1" in output


@pytest.mark.asyncio
async def test_providers_lists_the_registered_provider(diagnostics: MCPDiagnostics) -> None:
    output, _ = await run_command(diagnostics, "providers")

    assert EXAMPLE_PROVIDER_ID in output
    assert "registered" in output


@pytest.mark.asyncio
async def test_capabilities_lists_what_jarvis_exposes(diagnostics: MCPDiagnostics) -> None:
    output, _ = await run_command(diagnostics, "capabilities")

    assert example_capability().name in output


@pytest.mark.asyncio
async def test_transports_distinguishes_registered_from_known(
    diagnostics: MCPDiagnostics,
) -> None:
    """All five types are described; only the wired one is registered.
    Conflating them would hide why a provider cannot connect."""
    output, _ = await run_command(diagnostics, "transports")
    registered = {line.split()[0] for line in output.splitlines()[2:] if line.split()[1] == "yes"}

    assert {"stdio", "websocket", "http", "ipc"} <= set(output.split())
    assert registered == {EXAMPLE_TRANSPORT_TYPE}


@pytest.mark.asyncio
async def test_empty_sections_render_as_none(diagnostics: MCPDiagnostics) -> None:
    output, code = await run_command(diagnostics, "connections")

    assert code == 0
    assert output == "(none)"


# --- Exit codes ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_exits_zero_when_only_warnings_exist(
    diagnostics: MCPDiagnostics,
) -> None:
    """A warning describes something that works. Exiting non-zero would
    make the command useless in a pre-commit hook."""
    output, code = await run_command(diagnostics, "validate")

    assert code == 0
    assert "warning(s)" in output
    assert "WARN" in output


@pytest.mark.asyncio
async def test_validate_exits_non_zero_on_a_real_error(platform: _Platform) -> None:
    """A provider whose transport nothing registered cannot connect --
    that is an error, and the shell must see it. Installed through the
    manager rather than the SDK helper, which would have refused it."""
    await platform.manager.install(
        "broken",
        ProviderMetadata(name="Broken", description="d", transport="websocket"),
        ProviderConfig(transport="websocket", options={"url": "ws://localhost:1"}),
    )

    output, code = await run_command(platform.diagnostics, "validate")

    assert code == 1
    assert "ERROR" in output
    assert "registry.transport_not_registered" in output


@pytest.mark.asyncio
async def test_inspect_without_a_target_is_a_usage_error(
    diagnostics: MCPDiagnostics,
) -> None:
    """Exit 2 is the shell convention for misuse, distinct from exit 1
    for 'ran fine, found nothing'."""
    output, code = await run_command(diagnostics, "inspect")

    assert code == 2
    assert "requires" in output


@pytest.mark.asyncio
async def test_inspect_of_an_unknown_id_reports_cleanly(
    diagnostics: MCPDiagnostics,
) -> None:
    output, code = await run_command(diagnostics, "inspect", "not-installed")

    assert code == 1
    assert "not-installed" in output
    assert "Traceback" not in output


@pytest.mark.asyncio
async def test_inspect_finds_a_provider_and_a_capability(
    diagnostics: MCPDiagnostics,
) -> None:
    """One command for both, because a developer debugging an id rarely
    knows which kind it is."""
    provider, provider_code = await run_command(diagnostics, "inspect", EXAMPLE_PROVIDER_ID)
    capability, capability_code = await run_command(
        diagnostics, "inspect", example_capability().name
    )

    assert (provider_code, capability_code) == (0, 0)
    assert json.loads(provider)["provider"]["provider_id"] == EXAMPLE_PROVIDER_ID
    assert json.loads(capability)["exposed_by_jarvis"] is True


# --- Security --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_command_prints_a_token(platform: _Platform) -> None:
    """Asserted over the raw output of every command, in both formats --
    a leak through an unexpected key would slip past a targeted check."""
    await platform.auth.authenticate(
        EXAMPLE_PROVIDER_ID, AuthMethod.BEARER_TOKEN, {"token": _TOKEN}
    )

    for command in _COMMANDS:
        target = EXAMPLE_PROVIDER_ID if command == "inspect" else ""
        for as_json in (False, True):
            output, _ = await run_command(platform.diagnostics, command, target, as_json=as_json)
            assert _TOKEN not in output, f"{command} (json={as_json}) leaked the token"


@pytest.mark.asyncio
async def test_auth_shows_status_without_the_credential(platform: _Platform) -> None:
    await platform.auth.authenticate(
        EXAMPLE_PROVIDER_ID, AuthMethod.BEARER_TOKEN, {"token": _TOKEN}
    )

    output, _ = await run_command(platform.diagnostics, "auth")

    assert EXAMPLE_PROVIDER_ID in output
    assert "yes" in output  # authenticated
    assert _TOKEN not in output


# --- Read-only -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_running_every_command_changes_nothing(diagnostics: MCPDiagnostics) -> None:
    """The CLI is safe to run against a live install; it must never be
    the thing that broke a provider."""
    before = (
        diagnostics.providers(),
        diagnostics.connections(),
        diagnostics.capabilities(),
        diagnostics.auth(),
    )

    for command in _COMMANDS:
        await run_command(diagnostics, command, EXAMPLE_PROVIDER_ID)

    assert (
        diagnostics.providers(),
        diagnostics.connections(),
        diagnostics.capabilities(),
        diagnostics.auth(),
    ) == before
