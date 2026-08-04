"""Provider Manager tests -- Milestone 10.5 Task Group C, deliverables
3, 7 and 8 (lifecycle, health, events).

Permission assertions run against the *real* M9 ``PermissionModel`` on a
real temp-file store: the deliverable is that there is no second
permission system, so a fake one would prove nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import MCPProviderStateChangedEvent
from jarvis.core.mcp.client import MCPClientRuntime
from jarvis.core.mcp.providers.manager import MCPProviderManager
from jarvis.core.mcp.providers.metadata import (
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
)
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.server import principal_for
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel


class _FakeTransport:
    transport_type = "stdio"

    def __init__(self, config: dict) -> None:
        self.config = config
        self._connected = False
        self.fail_connect = bool(config.get("fail_connect"))

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self.fail_connect:
            raise OSError("peer refused")
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def request(self, method: str, params: dict | None = None) -> dict:
        if method == "initialize":
            return {"server_id": "peer", "agreed_version": "2025-06-18"}
        if method == "capabilities/list":
            return {
                "capabilities": [
                    {"name": "echo", "kind": "tool", "permissions": ["agent_tools"]},
                ]
            }
        return {"pong": True}


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def permissions(bus: EventBus, tmp_path: Path) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "perm.json")


@pytest.fixture
def manager(bus: EventBus, permissions: PermissionModel) -> MCPProviderManager:
    transports = TransportFactoryRegistry()
    transports.register("stdio", _FakeTransport)
    return MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=transports,
        permission_model=permissions,
        event_bus=bus,
    )


def _meta(**kwargs: object) -> ProviderMetadata:
    return ProviderMetadata(
        name=kwargs.pop("name", "Demo"),  # type: ignore[arg-type]
        required_permissions=kwargs.pop("required_permissions", ("agent_tools",)),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


# --- Install / remove ----------------------------------------------------------


@pytest.mark.asyncio
async def test_install_registers_and_declares_permissions(
    manager: MCPProviderManager, permissions: PermissionModel
) -> None:
    """Installing declares requested scopes as PENDING in the shared
    store -- never grants them."""
    record = await manager.install("demo", _meta())

    assert record.state is ProviderState.REGISTERED
    assert ("mcp:demo", "agent_tools") in permissions.pending()
    assert manager.resolve_scopes("demo") == set()
    assert manager.pending_scopes("demo") == ("agent_tools",)


@pytest.mark.asyncio
async def test_install_binds_the_generic_provider_implementation(
    manager: MCPProviderManager,
) -> None:
    record = await manager.install("demo", _meta())
    assert record.provider is not None
    assert record.provider.provider_id == "demo"


@pytest.mark.asyncio
async def test_remove_stops_then_deregisters(manager: MCPProviderManager) -> None:
    """Removing a running provider without stopping it would leak its
    transport, so the order is not optional."""
    await manager.install("demo", _meta())
    await manager.connect("demo")

    assert await manager.remove("demo") is True
    assert manager.registry.has("demo") is False


@pytest.mark.asyncio
async def test_removing_an_unknown_provider_returns_false(manager: MCPProviderManager) -> None:
    assert await manager.remove("nope") is False


# --- Lifecycle -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_lifecycle_transitions(manager: MCPProviderManager) -> None:
    await manager.install("demo", _meta())

    assert await manager.initialize("demo") is True
    assert manager.registry.require("demo").state is ProviderState.INITIALIZED

    assert await manager.connect("demo") is True
    assert manager.registry.require("demo").state is ProviderState.CONNECTED

    assert await manager.suspend("demo") is True
    assert manager.registry.require("demo").state is ProviderState.SUSPENDED

    assert await manager.resume("demo") is True
    assert manager.registry.require("demo").state is ProviderState.CONNECTED

    assert await manager.disconnect("demo") is True
    assert manager.registry.require("demo").state is ProviderState.DISCONNECTED


@pytest.mark.asyncio
async def test_connect_initializes_implicitly(manager: MCPProviderManager) -> None:
    await manager.install("demo", _meta())

    assert await manager.connect("demo") is True


@pytest.mark.asyncio
async def test_connecting_a_disabled_provider_is_refused(manager: MCPProviderManager) -> None:
    await manager.install("demo", _meta(), ProviderConfig(enabled=False))

    with pytest.raises(MCPProviderError, match="disabled"):
        await manager.connect("demo")


@pytest.mark.asyncio
async def test_suspend_is_idempotent(manager: MCPProviderManager) -> None:
    await manager.install("demo", _meta())
    await manager.connect("demo")

    assert await manager.suspend("demo") is True
    assert await manager.suspend("demo") is True


@pytest.mark.asyncio
async def test_resuming_a_provider_that_is_not_suspended_is_refused(
    manager: MCPProviderManager,
) -> None:
    await manager.install("demo", _meta())
    await manager.connect("demo")

    with pytest.raises(MCPProviderError, match="not suspended"):
        await manager.resume("demo")


@pytest.mark.asyncio
async def test_a_failing_connect_lands_in_failed_with_a_reason(
    manager: MCPProviderManager,
) -> None:
    await manager.install("demo", _meta(), ProviderConfig(options={"fail_connect": True}))

    assert await manager.connect("demo") is False

    record = manager.registry.require("demo")
    assert record.state is ProviderState.FAILED
    assert "peer refused" in record.error


@pytest.mark.asyncio
async def test_missing_transport_fails_the_provider_not_the_framework() -> None:
    """An empty transport registry must fail this provider, not raise
    out of the manager."""
    bus = EventBus()
    manager = MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=TransportFactoryRegistry(),  # nothing registered
        permission_model=PermissionModel(bus, store_path=Path("/nonexistent/perm.json")),
        event_bus=bus,
    )
    await manager.install("demo", _meta())

    assert await manager.initialize("demo") is False
    assert "not registered" in manager.registry.require("demo").error


# --- Batch operations ----------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_all_is_fault_isolated(manager: MCPProviderManager) -> None:
    """One provider failing never stops another's -- the same isolation
    ``PluginRegistry.discover_and_load_all`` established."""
    await manager.install("good", _meta())
    await manager.install("bad", _meta(), ProviderConfig(options={"fail_connect": True}))
    await manager.install("off", _meta(), ProviderConfig(enabled=False))

    results = await manager.connect_all()

    assert results == {"good": True, "bad": False}  # disabled one is skipped entirely
    assert manager.registry.require("good").state is ProviderState.CONNECTED
    assert manager.registry.require("bad").state is ProviderState.FAILED


@pytest.mark.asyncio
async def test_disconnect_all_covers_connected_providers(manager: MCPProviderManager) -> None:
    await manager.install("a", _meta())
    await manager.install("b", _meta())
    await manager.connect_all()

    await manager.disconnect_all()

    assert all(r.state is ProviderState.DISCONNECTED for r in manager.registry.enumerate())


# --- Permissions ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_granting_a_scope_takes_effect_on_the_next_connect(
    manager: MCPProviderManager, permissions: PermissionModel
) -> None:
    """Scopes resolve fresh per connect, so a grant made after
    installation works without re-registering the provider."""
    await manager.install("demo", _meta())
    await manager.connect("demo")
    assert manager.resolve_scopes("demo") == set()

    await permissions.grant(principal_for("demo"), "agent_tools")
    await manager.disconnect("demo")
    await manager.connect("demo")

    assert manager.resolve_scopes("demo") == {"agent_tools"}
    assert manager.pending_scopes("demo") == ()


@pytest.mark.asyncio
async def test_ungranted_capability_is_filtered_out_of_the_connection(
    manager: MCPProviderManager, permissions: PermissionModel
) -> None:
    await manager.install("demo", _meta())
    await manager.connect("demo")

    status = await manager.status("demo")
    assert status["detail"]["capabilities"] == []

    await permissions.grant(principal_for("demo"), "agent_tools")
    await manager.disconnect("demo")
    await manager.connect("demo")

    status = await manager.status("demo")
    assert status["detail"]["capabilities"] == ["echo"]


# --- Health --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_reports_a_connected_provider_healthy(
    manager: MCPProviderManager,
) -> None:
    await manager.install("demo", _meta())
    await manager.connect("demo")

    health = await manager.health("demo")
    assert health == {
        "provider_id": "demo",
        "state": "connected",
        "healthy": True,
        "detail": "",
    }


@pytest.mark.asyncio
async def test_health_reports_an_uninitialized_provider_unhealthy(
    manager: MCPProviderManager,
) -> None:
    await manager.install("demo", _meta())

    health = await manager.health("demo")
    assert health["healthy"] is False


@pytest.mark.asyncio
async def test_collect_health_is_the_single_collector_payload(
    manager: MCPProviderManager,
) -> None:
    await manager.install("good", _meta())
    await manager.install("idle", _meta())
    await manager.connect("good")

    payload = await manager.collect_health()

    assert payload["count"] == 2
    assert payload["connected"] == ["good"]
    assert payload["unhealthy"] == ["idle"]


@pytest.mark.asyncio
async def test_status_includes_granted_and_pending_permissions(
    manager: MCPProviderManager,
) -> None:
    await manager.install("demo", _meta())

    status = await manager.status("demo")

    assert status["pending_permissions"] == ["agent_tools"]
    assert status["granted_permissions"] == []


# --- Events --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_lifecycle_transition_publishes_its_action(
    manager: MCPProviderManager, bus: EventBus
) -> None:
    seen: list[MCPProviderStateChangedEvent] = []
    bus.subscribe(MCPProviderStateChangedEvent, seen.append)

    await manager.install("demo", _meta())
    await manager.initialize("demo")
    await manager.connect("demo")
    await manager.suspend("demo")
    await manager.resume("demo")
    await manager.disconnect("demo")
    await manager.remove("demo")

    actions = [e.action for e in seen]
    assert actions == [
        "registered",
        "initialized",
        "connected",
        "suspended",
        "resumed",
        "disconnected",
        # remove() tears the provider down internally and reports the
        # one action the caller actually asked for -- emitting a
        # spurious second 'disconnected' first would be noise.
        "removed",
    ]


@pytest.mark.asyncio
async def test_resumed_action_reports_connected_state(
    manager: MCPProviderManager, bus: EventBus
) -> None:
    """The transition and the resting state genuinely differ here."""
    seen: list[MCPProviderStateChangedEvent] = []
    bus.subscribe(MCPProviderStateChangedEvent, seen.append)

    await manager.install("demo", _meta())
    await manager.connect("demo")
    await manager.suspend("demo")
    await manager.resume("demo")

    resumed = next(e for e in seen if e.action == "resumed")
    assert resumed.state == "connected"


@pytest.mark.asyncio
async def test_failure_publishes_a_failed_action_with_detail(
    manager: MCPProviderManager, bus: EventBus
) -> None:
    seen: list[MCPProviderStateChangedEvent] = []
    bus.subscribe(MCPProviderStateChangedEvent, seen.append)

    await manager.install("demo", _meta(), ProviderConfig(options={"fail_connect": True}))
    await manager.connect("demo")

    failed = next(e for e in seen if e.action == "failed")
    assert failed.state == "failed"
    assert "peer refused" in failed.detail


@pytest.mark.asyncio
async def test_manager_works_without_an_event_bus(permissions: PermissionModel) -> None:
    transports = TransportFactoryRegistry()
    transports.register("stdio", _FakeTransport)
    manager = MCPProviderManager(
        MCPProviderRegistry(),
        client_runtime=MCPClientRuntime(),
        transport_registry=transports,
        permission_model=permissions,
        event_bus=None,
    )

    await manager.install("demo", _meta())
    assert await manager.connect("demo") is True
