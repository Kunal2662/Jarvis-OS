"""Example implementation tests -- Milestone 10.5 Task Group E,
deliverable 4.

These exist so the examples cannot rot. A sample in a document breaks
silently the moment an API changes; these are imported and executed, so
the same change breaks the build instead.

They also assert the *self-contained* property the task group requires:
no example opens a socket, spawns a process, reads the environment, or
names a real service.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.mcp import TRANSPORT_TYPES, MCPTransportError
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.metadata import ProviderState
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.sdk import validate_capability, validate_provider_metadata
from jarvis.core.mcp.sdk.examples import (
    EXAMPLE_PROVIDER_ID,
    EXAMPLE_TRANSPORT_TYPE,
    ExampleAuthStrategy,
    ExampleTransport,
    build_example_transport,
    example_capability,
    example_capability_invoker,
    example_config,
    example_provider,
)
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "perm.json")


# --- The examples are valid by the SDK's own rules -------------------------------


def test_example_capability_passes_validation() -> None:
    """An example that would not validate teaches the wrong thing."""
    assert validate_capability(example_capability()).issues == ()


def test_example_provider_passes_validation() -> None:
    assert validate_provider_metadata(example_provider()).issues == ()


def test_example_config_resolves_the_example_transport() -> None:
    metadata = example_provider()

    assert example_config().resolved_transport(metadata) == EXAMPLE_TRANSPORT_TYPE


def test_example_does_not_invent_a_transport_type() -> None:
    """``TRANSPORT_TYPES`` is closed by design; an example that widened
    it would teach an author to do something the platform rejects."""
    assert EXAMPLE_TRANSPORT_TYPE in TRANSPORT_TYPES


def test_example_provider_declares_the_capability_it_offers() -> None:
    assert example_capability().name in example_provider().capabilities


# --- Self-containment ------------------------------------------------------------


def test_examples_import_no_network_or_process_machinery() -> None:
    """The guarantee is 'connects to nothing'. Asserted against the
    module source rather than trusted from the docstring."""
    from jarvis.core.mcp.sdk import examples

    source = inspect.getsource(examples)

    for forbidden in ("import socket", "import httpx", "subprocess", "os.environ", "websockets"):
        assert forbidden not in source, f"examples must not use {forbidden}"


@pytest.mark.asyncio
async def test_example_invoker_is_a_pure_function_of_its_input() -> None:
    assert await example_capability_invoker({"text": "hi"}) == {"echoed": "hi"}
    assert await example_capability_invoker({}) == {"echoed": ""}


# --- ExampleTransport ------------------------------------------------------------


@pytest.mark.asyncio
async def test_example_transport_answers_the_full_handshake() -> None:
    """It is a usable ``IMCPTransport``, not a stub that returns
    ``None`` -- which is what makes it a legitimate test double for the
    real client runtime."""
    transport = build_example_transport({})
    await transport.connect()

    assert transport.is_connected is True
    assert (await transport.request("initialize"))["agreed_version"]
    assert (await transport.request("capabilities/list"))["capabilities"][0]["name"] == (
        example_capability().name
    )
    assert (await transport.request("ping"))["pong"] is True
    assert await transport.request("capabilities/call", {"arguments": {"text": "yo"}}) == {
        "result": {"echoed": "yo"}
    }

    await transport.disconnect()
    assert transport.is_connected is False


@pytest.mark.asyncio
async def test_example_transport_refuses_requests_while_disconnected() -> None:
    """Reporting the truth beats fabricating a response -- the same rule
    every shipped transport follows."""
    with pytest.raises(MCPTransportError, match="disconnected"):
        await ExampleTransport().request("ping")


@pytest.mark.asyncio
async def test_example_transport_rejects_an_unknown_method() -> None:
    transport = ExampleTransport()
    await transport.connect()

    with pytest.raises(MCPTransportError, match="unknown method"):
        await transport.request("does/not/exist")


@pytest.mark.asyncio
async def test_example_provider_installs_and_connects_end_to_end(
    permissions: PermissionModel,
) -> None:
    """The example is exercised through the *real* provider manager and
    client runtime, so it proves the SDK's output is what the platform
    actually consumes."""
    transports = TransportFactoryRegistry()
    transports.register(EXAMPLE_TRANSPORT_TYPE, build_example_transport)
    manager = MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=transports,
        permission_model=permissions,
    )

    await manager.install(EXAMPLE_PROVIDER_ID, example_provider(), example_config())

    assert await manager.connect(EXAMPLE_PROVIDER_ID) is True
    assert manager.registry.require(EXAMPLE_PROVIDER_ID).state is ProviderState.CONNECTED

    await manager.disconnect(EXAMPLE_PROVIDER_ID)
    assert manager.registry.require(EXAMPLE_PROVIDER_ID).state is ProviderState.DISCONNECTED


# --- ExampleAuthStrategy ---------------------------------------------------------


@pytest.mark.asyncio
async def test_example_strategy_mints_and_refreshes_locally() -> None:
    """The shipped static strategies refuse to refresh, so the example
    is where a working ``refresh`` can be read."""
    strategy = ExampleAuthStrategy()

    credential = await strategy.authenticate("demo", {})
    refreshed = await strategy.refresh(credential)

    assert credential.access_token != refreshed.access_token
    assert strategy.validate(refreshed) is True


@pytest.mark.asyncio
async def test_example_strategy_revoke_clears_the_token() -> None:
    strategy = ExampleAuthStrategy()
    credential = await strategy.authenticate("demo", {"token": "supplied"})

    revoked = await strategy.revoke(credential)

    assert revoked.has_access_token is False
    assert strategy.validate(revoked) is False


def test_example_strategy_claims_only_what_it_implements() -> None:
    """It issues a bearer token, so it says ``BEARER_TOKEN``. Claiming
    an unimplemented flow such as OAuth2 would make
    ``/api/v1/mcp/auth/methods`` report a capability that does not
    exist."""
    assert ExampleAuthStrategy.method is AuthMethod.BEARER_TOKEN


def test_registering_the_example_strategy_needs_a_deliberate_replace() -> None:
    """The collision is the point: the registry refuses to silently
    shadow the shipped bearer-token strategy."""
    from jarvis.core.mcp.auth.credentials import MCPAuthError

    strategies = build_default_strategy_registry()

    with pytest.raises(MCPAuthError, match="already registered"):
        strategies.register(ExampleAuthStrategy())

    strategies.register(ExampleAuthStrategy(), replace=True)
    assert isinstance(strategies.get(AuthMethod.BEARER_TOKEN), ExampleAuthStrategy)
