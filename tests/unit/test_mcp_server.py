"""Unit tests for the MCP Server Runtime -- Milestone 10.5 Task Group A,
deliverables 4 (server lifecycle) and 6 (permission model reuse).

Every permission assertion here runs against the *real* M9
``PermissionModel`` on a real temp-file store -- the point of the
deliverable is that there is no second permission system, so testing
against a fake one would prove nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import MCPPermissionDeniedEvent
from jarvis.core.interfaces.mcp import MCPCapability, MCPError
from jarvis.core.mcp.server import MCPServerRuntime, principal_for
from jarvis.core.plugins.permissions import PermissionModel


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def permissions(bus: EventBus, tmp_path: Path) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "perm.json")


@pytest.fixture
def server(permissions: PermissionModel, bus: EventBus) -> MCPServerRuntime:
    return MCPServerRuntime(permission_model=permissions, event_bus=bus)


async def _echo(params: dict[str, Any]) -> dict[str, Any]:
    return {"echoed": params.get("text", "")}


# --- Lifecycle ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_starts_and_stops_idempotently(server: MCPServerRuntime) -> None:
    assert server.is_running is False
    assert (await server.health()).healthy is False

    await server.start()
    await server.start()
    assert server.is_running is True
    assert (await server.health()).healthy is True

    await server.stop()
    await server.stop()
    assert server.is_running is False


@pytest.mark.asyncio
async def test_requests_are_refused_while_stopped(server: MCPServerRuntime) -> None:
    with pytest.raises(MCPError, match="not running"):
        await server.handle_request("initialize", {}, client_id="c1")


@pytest.mark.asyncio
async def test_status_reports_capabilities_and_methods(server: MCPServerRuntime) -> None:
    await server.start()
    await server.expose(MCPCapability(name="echo"), _echo)

    status = await server.status()

    assert status.state == "running"
    assert status.detail["capability_count"] == 1
    assert status.detail["capabilities"] == ["echo"]
    assert set(status.detail["methods"]) == {
        "initialize",
        "capabilities/list",
        "capabilities/call",
    }


# --- Capability exposure ------------------------------------------------------


@pytest.mark.asyncio
async def test_expose_then_revoke(server: MCPServerRuntime) -> None:
    await server.expose(MCPCapability(name="echo"), _echo)
    assert server.capabilities.has("echo")

    assert await server.revoke("echo") is True
    assert await server.revoke("echo") is False
    assert not server.capabilities.has("echo")


@pytest.mark.asyncio
async def test_capability_without_invoker_is_discoverable_but_not_callable(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    """Reporting the gap honestly beats returning a fabricated result."""
    await server.start()
    await server.expose(MCPCapability(name="listed_only"))

    assert server.capabilities.has("listed_only")
    with pytest.raises(MCPError, match="no invoker bound"):
        await server.invoke("listed_only", {}, client_id="c1")


# --- Permission enforcement (deliverable 6) ----------------------------------


@pytest.mark.asyncio
async def test_declaring_uses_the_shared_store_with_an_mcp_namespace(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    """MCP principals live in the same ``PermissionModel`` a plugin
    does, namespaced so the two identity spaces cannot collide."""
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)
    server.declare_for("c1")

    assert ("mcp:c1", "agent_tools") in permissions.pending()
    assert principal_for("c1") == "mcp:c1"


@pytest.mark.asyncio
async def test_declared_scope_is_pending_not_granted(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    """Least-privilege: declaring is a request, never a grant."""
    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)
    server.declare_for("c1")

    permitted, reason = await server.check_permitted("c1", "echo")
    assert permitted is False
    assert "not granted" in reason
    assert server.granted_scopes("c1") == set()


@pytest.mark.asyncio
async def test_granting_makes_the_capability_invocable(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)
    await permissions.grant(principal_for("c1"), "agent_tools")

    permitted, _ = await server.check_permitted("c1", "echo")
    assert permitted is True
    assert server.granted_scopes("c1") == {"agent_tools"}
    assert await server.invoke("echo", {"text": "hi"}, client_id="c1") == {
        "result": {"echoed": "hi"}
    }


@pytest.mark.asyncio
async def test_grant_is_per_principal(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)
    await permissions.grant(principal_for("c1"), "agent_tools")

    assert (await server.check_permitted("c1", "echo"))[0] is True
    assert (await server.check_permitted("c2", "echo"))[0] is False


@pytest.mark.asyncio
async def test_revoked_grant_blocks_again(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)
    await permissions.grant(principal_for("c1"), "agent_tools")
    await permissions.revoke(principal_for("c1"), "agent_tools")

    with pytest.raises(MCPError, match="not granted"):
        await server.invoke("echo", {}, client_id="c1")


@pytest.mark.asyncio
async def test_denial_publishes_an_observable_event(
    server: MCPServerRuntime, bus: EventBus
) -> None:
    """A refusal must be visible over the runtime relay, not only in a
    log line."""
    seen: list[MCPPermissionDeniedEvent] = []
    bus.subscribe(MCPPermissionDeniedEvent, seen.append)

    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("network",)), _echo)
    await server.check_permitted("c1", "echo")

    assert len(seen) == 1
    assert seen[0].principal == "mcp:c1"
    assert seen[0].capability == "echo"
    assert seen[0].scope == "network"


@pytest.mark.asyncio
async def test_unknown_capability_is_refused(server: MCPServerRuntime) -> None:
    await server.start()
    permitted, reason = await server.check_permitted("c1", "nope")
    assert permitted is False
    assert "Unknown capability" in reason


# --- Protocol dispatch -------------------------------------------------------


@pytest.mark.asyncio
async def test_initialize_negotiates_and_declares(
    server: MCPServerRuntime, permissions: PermissionModel
) -> None:
    await server.start()
    await server.expose(MCPCapability(name="echo", permissions=("agent_tools",)), _echo)

    response = await server.handle_request(
        "initialize", {"protocol_versions": ["2025-06-18"]}, client_id="c1"
    )

    assert response["agreed_version"] == "2025-06-18"
    assert response["server_id"] == "jarvis"
    # Connecting declares what the client would need -- as PENDING.
    assert ("mcp:c1", "agent_tools") in permissions.pending()


@pytest.mark.asyncio
async def test_initialize_reports_version_mismatch_without_raising(
    server: MCPServerRuntime,
) -> None:
    await server.start()
    response = await server.handle_request(
        "initialize", {"protocol_versions": ["1999-01-01"]}, client_id="c1"
    )

    assert response["agreed_version"] == ""
    assert "No shared protocol version" in response["failure_reason"]


@pytest.mark.asyncio
async def test_capabilities_list_filters_by_kind(server: MCPServerRuntime) -> None:
    await server.start()
    await server.expose(MCPCapability(name="t", kind="tool"))
    await server.expose(MCPCapability(name="r", kind="resource"))

    response = await server.handle_request("capabilities/list", {"kind": "resource"}, client_id="c")

    assert [c["name"] for c in response["capabilities"]] == ["r"]


@pytest.mark.asyncio
async def test_capabilities_call_requires_a_name(server: MCPServerRuntime) -> None:
    await server.start()
    with pytest.raises(MCPError, match="requires a 'name'"):
        await server.handle_request("capabilities/call", {}, client_id="c1")


@pytest.mark.asyncio
async def test_unknown_method_raises(server: MCPServerRuntime) -> None:
    await server.start()
    with pytest.raises(MCPError, match="Unknown MCP method"):
        await server.handle_request("does/not/exist", {}, client_id="c1")


@pytest.mark.asyncio
async def test_register_method_extends_the_protocol_surface(server: MCPServerRuntime) -> None:
    """A later task group adds a method without editing the dispatch."""

    async def _ping(params: dict[str, Any], client_id: str) -> dict[str, Any]:
        return {"pong": client_id}

    server.register_method("ping", _ping)
    await server.start()

    assert await server.handle_request("ping", {}, client_id="c9") == {"pong": "c9"}
