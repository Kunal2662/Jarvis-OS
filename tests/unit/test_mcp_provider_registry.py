"""Provider Registry tests -- Milestone 10.5 Task Group C, deliverables
2 and 6."""

from __future__ import annotations

import pytest

from jarvis.core.mcp.providers.metadata import (
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
)
from jarvis.core.mcp.providers.registry import MCPProviderRegistry


@pytest.fixture
def registry() -> MCPProviderRegistry:
    return MCPProviderRegistry()


def _meta(name: str = "demo", **kwargs: object) -> ProviderMetadata:
    return ProviderMetadata(name=name, **kwargs)  # type: ignore[arg-type]


# --- Registration --------------------------------------------------------------


def test_register_then_lookup(registry: MCPProviderRegistry) -> None:
    record = registry.register("demo", _meta())

    assert registry.has("demo")
    assert registry.get("demo") is record
    assert registry.provider_ids == ("demo",)
    assert len(registry) == 1


def test_registration_is_inert(registry: MCPProviderRegistry) -> None:
    """A registered provider has been declared, not started -- no
    transport, no subprocess, no socket. That is what makes discovery
    side-effect free."""
    record = registry.register("demo", _meta())

    assert record.state is ProviderState.REGISTERED
    assert record.provider is None


def test_duplicate_id_is_an_error_unless_replace(registry: MCPProviderRegistry) -> None:
    """A provider shadowing another's id would change what an existing
    permission grant and connection refer to."""
    registry.register("demo", _meta(version="1.0.0"))

    with pytest.raises(MCPProviderError, match="already registered"):
        registry.register("demo", _meta(version="2.0.0"))

    registry.register("demo", _meta(version="2.0.0"), replace=True)
    assert registry.require("demo").metadata.version == "2.0.0"


def test_register_rejects_an_empty_id(registry: MCPProviderRegistry) -> None:
    with pytest.raises(MCPProviderError, match="id must not be empty"):
        registry.register("  ", _meta())


def test_register_validates_metadata_and_config(registry: MCPProviderRegistry) -> None:
    with pytest.raises(MCPProviderError, match="unknown transport"):
        registry.register("demo", _meta(transport="carrier_pigeon"))

    with pytest.raises(MCPProviderError, match="unknown transport"):
        registry.register("demo", _meta(), ProviderConfig(transport="carrier_pigeon"))


def test_unregister_reports_whether_it_existed(registry: MCPProviderRegistry) -> None:
    registry.register("demo", _meta())

    assert registry.unregister("demo") is True
    assert registry.unregister("demo") is False


def test_require_raises_with_the_id_named(registry: MCPProviderRegistry) -> None:
    with pytest.raises(MCPProviderError, match="'missing' is not registered"):
        registry.require("missing")


def test_clear_empties_the_registry(registry: MCPProviderRegistry) -> None:
    registry.register("a", _meta("a"))
    registry.register("b", _meta("b"))
    registry.clear()

    assert len(registry) == 0


def test_metadata_lookup(registry: MCPProviderRegistry) -> None:
    registry.register("demo", _meta(author="someone"))

    metadata = registry.metadata("demo")
    assert metadata is not None
    assert metadata.author == "someone"
    assert registry.metadata("missing") is None


# --- Discovery -----------------------------------------------------------------


@pytest.fixture
def populated() -> MCPProviderRegistry:
    registry = MCPProviderRegistry()
    registry.register(
        "alpha",
        _meta(
            "alpha",
            transport="stdio",
            capabilities=("echo",),
            required_permissions=("agent_tools",),
        ),
    )
    registry.register(
        "beta",
        _meta("beta", transport="http", capabilities=("fetch",), required_permissions=("network",)),
        ProviderConfig(enabled=False),
    )
    registry.register("gamma", _meta("gamma", transport="stdio", capabilities=("echo", "fetch")))
    registry.require("gamma").state = ProviderState.CONNECTED
    return registry


def _ids(records) -> list[str]:
    return sorted(r.provider_id for r in records)


def test_discover_without_filters_returns_everything(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover()) == ["alpha", "beta", "gamma"]


def test_discover_by_transport(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(transport="stdio")) == ["alpha", "gamma"]


def test_discover_by_capability(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(capability="fetch")) == ["beta", "gamma"]


def test_discover_by_state_accepts_enum_or_string(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(state=ProviderState.CONNECTED)) == ["gamma"]
    assert _ids(populated.discover(state="connected")) == ["gamma"]


def test_discover_by_protocol(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(protocol="2025-06-18")) == ["alpha", "beta", "gamma"]
    assert _ids(populated.discover(protocol="1999-01-01")) == []


def test_discover_by_permission_scope(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(permission="network")) == ["beta"]


def test_discover_enabled_only(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(enabled_only=True)) == ["alpha", "gamma"]


def test_discover_filters_combine_with_and(populated: MCPProviderRegistry) -> None:
    assert _ids(populated.discover(transport="stdio", capability="fetch")) == ["gamma"]
    assert _ids(populated.discover(transport="http", capability="echo")) == []


def test_discover_respects_a_config_transport_override() -> None:
    """Discovery must filter on the *resolved* transport, not the
    metadata's declared default -- otherwise an overridden provider
    would be findable under a transport it does not actually use."""
    registry = MCPProviderRegistry()
    registry.register("demo", _meta(transport="stdio"), ProviderConfig(transport="websocket"))

    assert _ids(registry.discover(transport="websocket")) == ["demo"]
    assert _ids(registry.discover(transport="stdio")) == []


def test_required_scopes_aggregates_across_providers(populated: MCPProviderRegistry) -> None:
    assert populated.required_scopes() == {"agent_tools", "network"}
    assert populated.required_scopes(["alpha"]) == {"agent_tools"}


def test_snapshot_is_serializable(populated: MCPProviderRegistry) -> None:
    rows = populated.snapshot()

    assert len(rows) == 3
    alpha = next(r for r in rows if r["provider_id"] == "alpha")
    assert alpha["transport"] == "stdio"
    assert alpha["state"] == "registered"
    assert alpha["metadata"]["capabilities"] == ["echo"]
