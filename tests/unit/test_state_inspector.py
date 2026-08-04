"""Unit tests for ``jarvis.core.devtools.state_inspector`` (Milestone 9
Task Group E)."""

from __future__ import annotations

import json

import pytest

from jarvis.core.devtools.state_inspector import StateInspector
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.interfaces.service import HealthStatus, ServiceStatus
from jarvis.core.lifecycle.runtime_manager import RuntimeManager
from jarvis.core.lifecycle.service_manager import ServiceManager
from jarvis.core.plugins.loader import PluginLoader
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.core.plugins.registry import PluginRegistry
from jarvis.core.plugins.sandbox import PluginSandbox


class _FakeService:
    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def health(self):
        return HealthStatus(healthy=True)

    async def status(self):
        return ServiceStatus(name="fake", state="ready")

    async def shutdown(self) -> None:
        pass


def test_snapshot_empty_when_nothing_wired():
    inspector = StateInspector()
    snapshot = inspector.snapshot()
    assert snapshot.services == ()
    assert snapshot.plugins == ()
    assert snapshot.startup_hooks == ()
    assert snapshot.shutdown_hooks == ()


@pytest.mark.asyncio
async def test_snapshot_reflects_service_manager():
    service_manager = ServiceManager(EventBus())
    service_manager.register("chat", _FakeService(), priority=10)
    await service_manager.start_all()

    inspector = StateInspector(service_manager=service_manager)
    snapshot = inspector.snapshot()

    assert len(snapshot.services) == 1
    assert snapshot.services[0].name == "chat"
    assert snapshot.services[0].state == "running"
    assert snapshot.plugins == ()


def test_snapshot_reflects_runtime_manager():
    runtime_manager = RuntimeManager()

    async def _noop() -> None:
        pass

    runtime_manager.register_startup("configuration_manager", _noop, priority=0)
    runtime_manager.register("configuration_manager", _noop, priority=0)

    inspector = StateInspector(runtime_manager=runtime_manager)
    snapshot = inspector.snapshot()

    assert snapshot.startup_hooks == ("configuration_manager",)
    assert snapshot.shutdown_hooks == ("configuration_manager",)
    assert snapshot.services == ()


@pytest.mark.asyncio
async def test_snapshot_reflects_plugin_registry(tmp_path):
    class _FakePlatformAdapter:
        def info(self):
            return PlatformInfo(
                family=PlatformFamily.WINDOWS,
                os_release="test",
                architecture="x86_64",
                python_version="3.13.0",
            )

        def has_capability(self, capability):
            return False

        def resolve_entry_point(self, entry_point, *, default_key="default"):
            return entry_point if isinstance(entry_point, str) else entry_point.get(default_key)

    plugins_dir = tmp_path / "plugins"
    plugin_dir = plugins_dir / "hello-world"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(
            {
                "name": "hello-world",
                "display_name": "Hello World",
                "version": "1.0.0",
                "entry_point": "plugin:HelloPlugin",
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "plugin.py").write_text(
        "class HelloPlugin:\n"
        "    async def on_load(self, context) -> None: pass\n"
        "    async def on_start(self) -> None: pass\n"
        "    async def on_stop(self) -> None: pass\n",
        encoding="utf-8",
    )

    event_bus = EventBus()
    registry = PluginRegistry(
        loader=PluginLoader(
            plugins_dir, platform_adapter=_FakePlatformAdapter(), app_version="0.11.0"
        ),
        sandbox=PluginSandbox(),
        permission_model=PermissionModel(event_bus, store_path=tmp_path / "permissions.json"),
        event_bus=event_bus,
        platform_adapter=_FakePlatformAdapter(),
        plugin_data_root=tmp_path / "plugin-data",
    )
    await registry.discover_and_load_all()

    inspector = StateInspector(plugin_registry=registry)
    snapshot = inspector.snapshot()

    assert len(snapshot.plugins) == 1
    assert snapshot.plugins[0].plugin_id == "hello-world"
    assert snapshot.plugins[0].state == "running"
