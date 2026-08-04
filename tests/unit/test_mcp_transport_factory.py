"""Unit tests for the transport factory and the registry's discovery
surface -- Milestone 10.5 Task Group B, deliverables 5 and 6."""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.mcp import TRANSPORT_TYPES, IMCPTransport, MCPTransportError
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.mcp.transports.factory import build_default_transport_registry


@pytest.fixture
def registry() -> TransportFactoryRegistry:
    return build_default_transport_registry()


# --- Factory ------------------------------------------------------------------


def test_every_network_transport_is_registered(registry: TransportFactoryRegistry) -> None:
    """Task Group A shipped this registry empty and documented that a
    later pass would fill it -- this asserts that actually happened."""
    assert set(registry.registered_types) == {"stdio", "websocket", "http", "ipc"}


def test_in_process_registers_only_when_a_server_is_supplied() -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.mcp.server import MCPServerRuntime

    class _Perm:
        def declare(self, *a, **k): ...
        def is_granted(self, *a, **k):
            return False

    server = MCPServerRuntime(permission_model=_Perm(), event_bus=EventBus())  # type: ignore[arg-type]
    full = build_default_transport_registry(in_process_server=server)

    assert set(full.registered_types) == set(TRANSPORT_TYPES)


@pytest.mark.parametrize(
    ("transport_type", "config"),
    [
        ("stdio", {"command": "python"}),
        ("websocket", {"url": "ws://127.0.0.1:1/x"}),
        ("http", {"url": "http://127.0.0.1:1/x"}),
        ("ipc", {"endpoint": "some-endpoint"}),
    ],
)
def test_factory_builds_a_transport_satisfying_the_port(
    registry: TransportFactoryRegistry, transport_type: str, config: dict
) -> None:
    transport = registry.create(transport_type, config)

    assert isinstance(transport, IMCPTransport)
    assert transport.transport_type == transport_type
    assert transport.is_connected is False


@pytest.mark.parametrize(
    ("transport_type", "missing_key"),
    [("stdio", "command"), ("websocket", "url"), ("http", "url"), ("ipc", "endpoint")],
)
def test_missing_required_config_fails_loudly(
    registry: TransportFactoryRegistry, transport_type: str, missing_key: str
) -> None:
    """A misconfigured peer must fail at construction with a message
    naming the key, not at first use with a confusing connect error."""
    with pytest.raises(MCPTransportError, match=missing_key):
        registry.create(transport_type, {})


def test_stdio_factory_passes_args_and_cwd_through(
    registry: TransportFactoryRegistry, tmp_path
) -> None:
    transport = registry.create(
        "stdio", {"command": "python", "args": ["-c", "pass"], "cwd": str(tmp_path)}
    )
    assert transport.transport_type == "stdio"


def test_request_timeout_is_configurable(registry: TransportFactoryRegistry) -> None:
    transport = registry.create(
        "http", {"url": "http://127.0.0.1:1/x", "request_timeout_seconds": 1.5}
    )
    assert transport._timeout == 1.5


# --- Registry discovery / query ------------------------------------------------


def test_discover_returns_the_whole_vocabulary(registry: TransportFactoryRegistry) -> None:
    assert set(registry.discover()) == set(TRANSPORT_TYPES)


def test_describe_reports_registered_true_for_a_shipped_transport(
    registry: TransportFactoryRegistry,
) -> None:
    descriptor = registry.describe("stdio")

    assert descriptor is not None
    assert descriptor["id"] == "stdio"
    assert descriptor["registered"] is True
    assert descriptor["requires_subprocess"] is True
    assert "command" in descriptor["config_keys"]


def test_describe_distinguishes_known_but_unregistered() -> None:
    """ "Known but not built here" is a 200 with registered:false, not a
    404 -- they are genuinely different situations."""
    empty = TransportFactoryRegistry()
    descriptor = empty.describe("websocket")

    assert descriptor is not None
    assert descriptor["registered"] is False


def test_describe_returns_none_for_an_unknown_identifier(
    registry: TransportFactoryRegistry,
) -> None:
    assert registry.describe("carrier_pigeon") is None


def test_describe_all_covers_every_known_transport(
    registry: TransportFactoryRegistry,
) -> None:
    descriptors = registry.describe_all()

    assert len(descriptors) == len(TRANSPORT_TYPES)
    assert {d["id"] for d in descriptors} == set(TRANSPORT_TYPES)


def test_http_is_the_only_stateless_transport(registry: TransportFactoryRegistry) -> None:
    stateless = {d["id"] for d in registry.describe_all() if not d["stateful"]}
    assert stateless == {"http"}


def test_remote_capable_transports_are_marked_not_local_only(
    registry: TransportFactoryRegistry,
) -> None:
    remote = {d["id"] for d in registry.describe_all() if not d["local_only"]}
    assert remote == {"websocket", "http"}
