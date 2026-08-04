"""SDK builder tests -- Milestone 10.5 Task Group E, deliverable 1.

The builders' contract is that they produce the *existing* runtime
models and refuse to produce an invalid one. Both halves are asserted:
the output is checked to be the real dataclass the runtime consumes, not
a lookalike, and every ``build()`` is checked to reject rather than
quietly emit something that fails later at connect time.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.mcp import MCPCapability
from jarvis.core.mcp.auth.credentials import AuthMethod, MCPAuthError
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata, ProviderState
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.sdk import (
    AuthBuilder,
    CapabilityBuilder,
    ConfigBuilder,
    ProviderBuilder,
    SDKValidationError,
    TransportBuilder,
    capability_names,
    expose_capabilities,
    register_provider,
)
from jarvis.core.mcp.sdk.examples import ExampleTransport
from jarvis.core.mcp.server import MCPServerRuntime
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "perm.json")


@pytest.fixture
def server(permissions: PermissionModel) -> MCPServerRuntime:
    return MCPServerRuntime(permission_model=permissions)


@pytest.fixture
def manager(permissions: PermissionModel) -> MCPProviderManager:
    transports = TransportFactoryRegistry()
    transports.register("in_process", ExampleTransport)
    return MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=transports,
        permission_model=permissions,
    )


# --- CapabilityBuilder ----------------------------------------------------------


def test_capability_builder_produces_the_runtime_model() -> None:
    """Not a lookalike: the object handed to ``server.expose`` must be
    the same dataclass the registry validates and serializes."""
    capability = (
        CapabilityBuilder("demo.echo")
        .version("2.0.0")
        .kind("tool")
        .describe("Echoes text.")
        .with_permission("agent_tools")
        .with_metadata(input_schema={"text": "string"})
        .build()
    )

    assert isinstance(capability, MCPCapability)
    assert capability.name == "demo.echo"
    assert capability.version == "2.0.0"
    assert capability.permissions == ("agent_tools",)
    assert capability.metadata["input_schema"] == {"text": "string"}


def test_repeated_permissions_collapse() -> None:
    """Declaring the same scope twice is a copy-paste slip, not an
    intent to require it twice."""
    capability = (
        CapabilityBuilder("demo.echo")
        .with_permission("agent_tools", "network", "agent_tools")
        .describe("x")
        .build()
    )

    assert capability.permissions == ("agent_tools", "network")


def test_build_rejects_an_unknown_scope_with_every_problem_at_once() -> None:
    """The whole list, not the first message -- an author fixing a
    provider wants one round trip."""
    builder = CapabilityBuilder("demo.echo").kind("widget").with_permission("teleport")

    with pytest.raises(SDKValidationError) as excinfo:
        builder.build()

    codes = {issue.code for issue in excinfo.value.report.errors}
    assert codes == {"capability.unknown_kind", "capability.unknown_permission"}


def test_draft_skips_validation_so_a_caller_can_inspect_first() -> None:
    builder = CapabilityBuilder("demo.echo").kind("widget")

    assert builder.draft().kind == "widget"
    assert builder.validate().ok is False


def test_warnings_do_not_block_build() -> None:
    """A missing description is worth reporting and not worth
    refusing."""
    capability = CapabilityBuilder("demo.echo").build()

    assert capability.description == ""


# --- ProviderBuilder ------------------------------------------------------------


def test_provider_builder_produces_the_runtime_model() -> None:
    metadata = (
        ProviderBuilder("Demo Service")
        .version("1.2.3")
        .author("Someone")
        .describe("A demo.")
        .transport("stdio")
        .with_permission("network")
        .with_tag("demo", "demo")
        .build()
    )

    assert isinstance(metadata, ProviderMetadata)
    assert metadata.version == "1.2.3"
    assert metadata.tags == ("demo",)  # duplicate collapsed


def test_with_capability_accepts_the_object_or_its_name() -> None:
    """An author who already built the capability should not have to
    re-type its name and risk a mismatch."""
    capability = CapabilityBuilder("demo.echo").describe("x").build()

    metadata = (
        ProviderBuilder("Demo")
        .describe("d")
        .with_capability(capability)
        .with_capability("demo.ping")
        .build()
    )

    assert metadata.capabilities == ("demo.echo", "demo.ping")


def test_provider_build_rejects_an_impossible_protocol_set() -> None:
    builder = ProviderBuilder("Demo").describe("d").with_protocols("1999-01-01")

    with pytest.raises(SDKValidationError, match="no_common_protocol"):
        builder.build()


# --- TransportBuilder -----------------------------------------------------------


def test_transport_builder_returns_a_config_not_a_live_transport() -> None:
    """``build()`` must never spawn a process or open a socket; a method
    with that name doing I/O would be a trap."""
    options = TransportBuilder("stdio").command("demo-server", "--stdio").timeout(5.0).build()

    assert options == {
        "command": "demo-server",
        "args": ["--stdio"],
        "request_timeout_seconds": 5.0,
    }


def test_transport_build_rejects_a_missing_required_option() -> None:
    with pytest.raises(SDKValidationError, match="missing_option"):
        TransportBuilder("websocket").build()


def test_transport_convenience_methods_map_to_the_right_keys() -> None:
    assert (
        TransportBuilder("websocket").url("ws://localhost:1").build()["url"] == "ws://localhost:1"
    )
    assert TransportBuilder("ipc").endpoint("pipe").build()["endpoint"] == "pipe"


# --- AuthBuilder ----------------------------------------------------------------


def test_auth_builder_redacts_the_secret_in_repr() -> None:
    """Same rule as ``Credential``: a token must not reach a log line
    through an incidental repr."""
    builder = AuthBuilder(AuthMethod.BEARER_TOKEN).token("tok_SUPER_SECRET").account("acct")

    assert "tok_SUPER_SECRET" not in repr(builder)
    assert "tok_SUPER_SECRET" not in str(builder)
    assert "token" in repr(builder)  # the key is safe to name


def test_auth_builder_coerces_a_string_method() -> None:
    """The typo should fail here, on construction, not several calls
    later where the value is finally compared."""
    assert AuthBuilder("bearer_token").method is AuthMethod.BEARER_TOKEN
    with pytest.raises(ValueError, match="bearer_tokn"):
        AuthBuilder("bearer_tokn")


def test_auth_build_requires_a_token_for_token_methods() -> None:
    with pytest.raises(MCPAuthError, match="missing_token"):
        AuthBuilder(AuthMethod.API_KEY).build()


def test_auth_build_returns_the_method_and_request() -> None:
    method, request = AuthBuilder(AuthMethod.BEARER_TOKEN).token("t").with_scope("a", "a").build()

    assert method is AuthMethod.BEARER_TOKEN
    assert request == {"token": "t", "scopes": ["a"]}


# --- ConfigBuilder --------------------------------------------------------------


def test_config_builder_composes_a_transport_builder() -> None:
    """The two builders compose rather than each re-stating the
    transport type."""
    config = (
        ConfigBuilder()
        .from_transport(TransportBuilder("stdio").command("demo-server"))
        .reconnect(max_attempts=5, backoff_seconds=0.1)
        .heartbeat(enabled=False)
        .build()
    )

    assert isinstance(config, ProviderConfig)
    assert config.transport == "stdio"
    assert config.options["command"] == "demo-server"
    assert config.reconnect.max_attempts == 5
    assert config.heartbeat.enabled is False


def test_config_build_validates_against_metadata_when_given() -> None:
    metadata = ProviderMetadata(name="Demo", description="d", transport="stdio")

    with pytest.raises(SDKValidationError, match="missing_transport_option"):
        ConfigBuilder("stdio").build(metadata)


def test_config_build_without_metadata_cannot_know_the_transport_needs() -> None:
    """No metadata means no resolved transport, so the option check is
    skipped rather than guessed at."""
    assert ConfigBuilder("stdio").build().transport == "stdio"


# --- Registry helpers -----------------------------------------------------------


@pytest.mark.asyncio
async def test_register_provider_installs_through_the_real_manager(
    manager: MCPProviderManager,
) -> None:
    metadata = (
        ProviderBuilder("Demo")
        .describe("d")
        .transport("in_process")
        .with_permission("agent_tools")
        .build()
    )
    config = ConfigBuilder("in_process").build(metadata)

    record = await register_provider(manager, "demo", metadata, config)

    assert record.state is ProviderState.REGISTERED
    assert manager.registry.has("demo")


@pytest.mark.asyncio
async def test_register_provider_rejects_before_touching_the_registry(
    manager: MCPProviderManager,
) -> None:
    """The cross-object check the manager cannot make on its own: each
    object is valid, the pair is not. Nothing must be registered."""
    metadata = ProviderBuilder("Demo").describe("d").transport("stdio").build()

    with pytest.raises(SDKValidationError, match="missing_transport_option"):
        await register_provider(manager, "demo", metadata, ProviderConfig(transport="stdio"))

    assert manager.registry.has("demo") is False


@pytest.mark.asyncio
async def test_register_provider_defaults_the_config(manager: MCPProviderManager) -> None:
    metadata = ProviderBuilder("Demo").describe("d").transport("in_process").build()

    record = await register_provider(manager, "demo", metadata)

    assert record.config.resolved_transport(metadata) == "in_process"


@pytest.mark.asyncio
async def test_expose_capabilities_is_all_or_nothing(server: MCPServerRuntime) -> None:
    """A partial exposure would leave the server offering half a feature
    set the author never intended to publish."""
    good = CapabilityBuilder("demo.good").describe("x").build()
    bad = MCPCapability(name="demo.bad", kind="widget", description="x")

    with pytest.raises(SDKValidationError):
        await expose_capabilities(server, [good, bad])

    assert capability_names(server.capabilities) == ()


@pytest.mark.asyncio
async def test_expose_capabilities_registers_the_whole_batch(server: MCPServerRuntime) -> None:
    one = CapabilityBuilder("demo.one").describe("x").build()
    two = CapabilityBuilder("demo.two").describe("x").build()

    names = await expose_capabilities(server, [one, two])

    assert names == ("demo.one", "demo.two")
    assert set(capability_names(server.capabilities)) == {"demo.one", "demo.two"}
