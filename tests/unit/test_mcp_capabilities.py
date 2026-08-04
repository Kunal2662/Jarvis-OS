"""Unit tests for the MCP Capability Registry -- Milestone 10.5 Task
Group A, deliverable 1."""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.mcp import MCPCapability, MCPCapabilityError
from jarvis.core.mcp.capabilities import MCPCapabilityRegistry


def _cap(name: str = "echo", **kwargs: object) -> MCPCapability:
    return MCPCapability(name=name, **kwargs)  # type: ignore[arg-type]


def test_register_then_get_and_has() -> None:
    registry = MCPCapabilityRegistry(owner="jarvis")
    registry.register(_cap("echo", description="Echoes input"))

    assert registry.has("echo")
    fetched = registry.get("echo")
    assert fetched is not None
    assert fetched.description == "Echoes input"
    assert len(registry) == 1
    assert registry.names == ("echo",)


def test_duplicate_registration_is_an_error_unless_replace() -> None:
    """A duplicate name silently winning would change what an existing
    permission grant actually authorizes -- so it must be deliberate."""
    registry = MCPCapabilityRegistry()
    registry.register(_cap("echo", version="1.0.0"))

    with pytest.raises(MCPCapabilityError, match="already registered"):
        registry.register(_cap("echo", version="2.0.0"))

    registry.register(_cap("echo", version="2.0.0"), replace=True)
    fetched = registry.get("echo")
    assert fetched is not None
    assert fetched.version == "2.0.0"


def test_unregister_reports_whether_it_existed() -> None:
    registry = MCPCapabilityRegistry()
    registry.register(_cap("echo"))

    assert registry.unregister("echo") is True
    assert registry.unregister("echo") is False
    assert not registry.has("echo")


def test_clear_empties_the_registry() -> None:
    registry = MCPCapabilityRegistry()
    registry.register_all([_cap("a"), _cap("b")])
    assert len(registry) == 2

    registry.clear()
    assert len(registry) == 0


def test_rejects_unknown_capability_kind() -> None:
    registry = MCPCapabilityRegistry()
    with pytest.raises(MCPCapabilityError, match="Unknown capability kind"):
        registry.register(MCPCapability(name="x", kind="not_a_kind"))


def test_rejects_permission_outside_the_existing_vocabulary() -> None:
    """M10.5 introduces no new permission vocabulary -- a capability may
    only declare scopes the plugin platform already defines."""
    registry = MCPCapabilityRegistry()
    with pytest.raises(MCPCapabilityError, match="Unknown permission scope"):
        registry.register(MCPCapability(name="x", permissions=("mcp.invent_a_scope",)))


def test_accepts_existing_permission_scopes() -> None:
    registry = MCPCapabilityRegistry()
    registry.register(MCPCapability(name="x", permissions=("agent_tools", "memory.read")))
    assert registry.has("x")


def test_rejects_empty_name() -> None:
    registry = MCPCapabilityRegistry()
    with pytest.raises(MCPCapabilityError, match="must not be empty"):
        registry.register(MCPCapability(name="   "))


def test_list_capabilities_filters_by_kind_and_permission() -> None:
    registry = MCPCapabilityRegistry()
    registry.register(MCPCapability(name="tool_a", kind="tool", permissions=("agent_tools",)))
    registry.register(MCPCapability(name="res_b", kind="resource", permissions=("memory.read",)))

    assert {c.name for c in registry.list_capabilities()} == {"tool_a", "res_b"}
    assert [c.name for c in registry.list_capabilities(kind="resource")] == ["res_b"]
    assert [c.name for c in registry.list_capabilities(required_permission="agent_tools")] == [
        "tool_a"
    ]


def test_snapshot_is_serializable_and_complete() -> None:
    registry = MCPCapabilityRegistry()
    registry.register(
        MCPCapability(
            name="echo",
            version="2.1.0",
            kind="tool",
            description="d",
            permissions=("agent_tools",),
            metadata={"k": "v"},
        )
    )

    (row,) = registry.snapshot()
    assert row == {
        "name": "echo",
        "version": "2.1.0",
        "kind": "tool",
        "description": "d",
        "permissions": ["agent_tools"],
        "metadata": {"k": "v"},
    }


def test_owner_isolates_two_registries() -> None:
    """The server's own capabilities and a peer's must never share one
    registry -- a misbehaving peer could otherwise shadow a JARVIS
    capability by name."""
    mine = MCPCapabilityRegistry(owner="jarvis")
    theirs = MCPCapabilityRegistry(owner="peer")

    mine.register(_cap("echo"))
    theirs.register(_cap("echo", description="peer's own"))

    assert mine.get("echo") is not theirs.get("echo")
    assert len(mine) == len(theirs) == 1
