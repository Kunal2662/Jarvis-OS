"""Unit tests for ``jarvis.core.plugins.registry`` (Milestone 9 Task
Group D, Phase 6) -- exercises the real Loader + Sandbox + Permission
Model stack together, not mocks of each other."""

from __future__ import annotations

import json

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import PluginLoadedEvent, PluginUpdatedEvent
from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.plugins.loader import PluginLoader
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.core.plugins.registry import PluginRegistry, PluginRegistryError, PluginState
from jarvis.core.plugins.sandbox import PluginSandbox

_GOOD_PLUGIN_PY = """
class HelloPlugin:
    started = False

    async def on_load(self, context) -> None:
        self.context = context

    async def on_start(self) -> None:
        HelloPlugin.started = True

    async def on_stop(self) -> None:
        HelloPlugin.started = False
"""

_FAILS_ON_START_PY = """
class HelloPlugin:
    async def on_load(self, context) -> None:
        pass

    async def on_start(self) -> None:
        raise RuntimeError("boom")

    async def on_stop(self) -> None:
        pass
"""


class _FakePlatformAdapter:
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            family=PlatformFamily.WINDOWS,
            os_release="test",
            architecture="x86_64",
            python_version="3.13.0",
        )

    def has_capability(self, capability: str) -> bool:
        return False

    def resolve_entry_point(self, entry_point, *, default_key="default"):
        return entry_point if isinstance(entry_point, str) else entry_point.get(default_key)


def _write_plugin(root, plugin_id, *, code=_GOOD_PLUGIN_PY, dependencies=(), permissions=()):
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_id,
        "display_name": plugin_id.title(),
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
        "dependencies": list(dependencies),
        "permissions": list(permissions),
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(code, encoding="utf-8")
    return plugin_dir


class _Harness:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.plugins_dir = tmp_path / "plugins"
        self.plugins_dir.mkdir()
        self.event_bus = EventBus()
        self.received = []
        loader = PluginLoader(
            self.plugins_dir, platform_adapter=_FakePlatformAdapter(), app_version="0.10.0"
        )
        sandbox = PluginSandbox()
        permission_model = PermissionModel(self.event_bus, store_path=tmp_path / "permissions.json")
        self.registry = PluginRegistry(
            loader=loader,
            sandbox=sandbox,
            permission_model=permission_model,
            event_bus=self.event_bus,
            platform_adapter=_FakePlatformAdapter(),
            plugin_data_root=tmp_path / "plugin-data",
        )

    def write_plugin(self, plugin_id, **kwargs):
        return _write_plugin(self.plugins_dir, plugin_id, **kwargs)

    def track(self, event_type):
        self.event_bus.subscribe(event_type, self.received.append)


def _harness(tmp_path) -> _Harness:
    return _Harness(tmp_path)


# ---- discover_and_load_all ----------------------------------------------------
@pytest.mark.asyncio
async def test_discover_and_load_all_runs_valid_plugin(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    h.track(PluginLoadedEvent)

    await h.registry.discover_and_load_all()

    snap = h.registry.snapshot()
    assert len(snap) == 1
    assert snap[0].plugin_id == "hello-world"
    assert snap[0].state == PluginState.RUNNING.value
    assert len(h.received) == 1


@pytest.mark.asyncio
async def test_missing_dependency_isolated_others_still_load(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("depends-on-ghost", dependencies=["ghost"])
    h.write_plugin("independent")

    await h.registry.discover_and_load_all()

    by_id = {s.plugin_id: s for s in h.registry.snapshot()}
    assert by_id["depends-on-ghost"].state == PluginState.FAILED.value
    assert by_id["independent"].state == PluginState.RUNNING.value


@pytest.mark.asyncio
async def test_on_start_exception_isolated_others_still_load(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("broken", code=_FAILS_ON_START_PY)
    h.write_plugin("healthy")

    await h.registry.discover_and_load_all()

    by_id = {s.plugin_id: s for s in h.registry.snapshot()}
    assert by_id["broken"].state == PluginState.FAILED.value
    assert "boom" in by_id["broken"].error
    assert by_id["healthy"].state == PluginState.RUNNING.value


# ---- enable / disable ----------------------------------------------------------
@pytest.mark.asyncio
async def test_disable_then_enable_round_trip(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value

    disabled = await h.registry.disable("hello-world")
    assert disabled is True
    assert h.registry.status("hello-world").state == PluginState.DISABLED.value
    assert h.registry.get_context("hello-world") is None

    enabled = await h.registry.enable("hello-world")
    assert enabled is True
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value


@pytest.mark.asyncio
async def test_disable_unknown_plugin_returns_false(tmp_path):
    h = _harness(tmp_path)
    assert await h.registry.disable("ghost") is False


# ---- install / uninstall ----------------------------------------------------------
@pytest.mark.asyncio
async def test_install_from_local_source_loads_it(tmp_path):
    h = _harness(tmp_path)
    source_dir = tmp_path / "staged" / "new-plugin"
    _write_plugin(tmp_path / "staged", "new-plugin")

    plugin_id = await h.registry.install(source_dir)

    assert plugin_id == "new-plugin"
    assert h.registry.status("new-plugin").state == PluginState.RUNNING.value
    assert (h.plugins_dir / "new-plugin" / "manifest.json").exists()


@pytest.mark.asyncio
async def test_install_already_installed_raises(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()

    source_dir = tmp_path / "staged" / "hello-world"
    _write_plugin(tmp_path / "staged", "hello-world")
    with pytest.raises(PluginRegistryError):
        await h.registry.install(source_dir)


@pytest.mark.asyncio
async def test_uninstall_removes_plugin_and_files(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()

    result = await h.registry.uninstall("hello-world")

    assert result is True
    assert h.registry.is_registered("hello-world") is False
    assert not (h.plugins_dir / "hello-world").exists()


@pytest.mark.asyncio
async def test_uninstall_unknown_plugin_returns_false(tmp_path):
    h = _harness(tmp_path)
    assert await h.registry.uninstall("ghost") is False


# ---- update / rollback ----------------------------------------------------------
@pytest.mark.asyncio
async def test_update_success_swaps_in_new_version(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()
    h.track(PluginUpdatedEvent)

    new_source = tmp_path / "staged" / "hello-world"
    plugin_dir = tmp_path / "staged" / "hello-world"
    plugin_dir.mkdir(parents=True)
    manifest = {
        "name": "hello-world",
        "display_name": "Hello World",
        "version": "2.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(_GOOD_PLUGIN_PY, encoding="utf-8")

    ok = await h.registry.update("hello-world", new_source)

    assert ok is True
    assert h.registry.status("hello-world").detail["version"] == "2.0.0"
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value
    assert len(h.received) == 1
    assert h.received[0].from_version == "1.0.0"
    assert h.received[0].to_version == "2.0.0"


@pytest.mark.asyncio
async def test_update_failure_rolls_back_to_last_known_good(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value

    broken_source = tmp_path / "staged" / "hello-world"
    _write_plugin(tmp_path / "staged", "hello-world", code=_FAILS_ON_START_PY)

    ok = await h.registry.update("hello-world", broken_source)

    assert ok is False
    # Rolled back: still running, still the original 1.0.0 version.
    assert h.registry.status("hello-world").state == PluginState.RUNNING.value
    assert h.registry.status("hello-world").detail["version"] == "1.0.0"
    assert (h.plugins_dir / "hello-world" / "manifest.json").exists()


@pytest.mark.asyncio
async def test_update_name_mismatch_raises(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()

    other_dir = tmp_path / "staged" / "different-name"
    _write_plugin(tmp_path / "staged", "different-name")

    with pytest.raises(PluginRegistryError):
        await h.registry.update("hello-world", other_dir)


@pytest.mark.asyncio
async def test_update_unknown_plugin_raises(tmp_path):
    h = _harness(tmp_path)
    source_dir = tmp_path / "staged" / "ghost"
    _write_plugin(tmp_path / "staged", "ghost")
    with pytest.raises(PluginRegistryError):
        await h.registry.update("ghost", source_dir)


# ---- health / status ----------------------------------------------------------
@pytest.mark.asyncio
async def test_health_running_is_healthy(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world")
    await h.registry.discover_and_load_all()
    assert h.registry.health("hello-world").healthy is True


@pytest.mark.asyncio
async def test_health_failed_is_unhealthy_with_detail(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("broken", code=_FAILS_ON_START_PY)
    await h.registry.discover_and_load_all()
    status = h.registry.health("broken")
    assert status.healthy is False
    assert "boom" in status.detail


def test_health_unknown_plugin(tmp_path):
    h = _harness(tmp_path)
    assert h.registry.health("ghost").healthy is False


# ---- snapshot / registered_ids ----------------------------------------------------------
@pytest.mark.asyncio
async def test_snapshot_includes_permissions(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("hello-world", permissions=["network"])
    await h.registry.discover_and_load_all()
    (snap,) = h.registry.snapshot()
    assert snap.permissions == ("network",)


@pytest.mark.asyncio
async def test_stop_all_disables_every_running_plugin(tmp_path):
    h = _harness(tmp_path)
    h.write_plugin("a")
    h.write_plugin("b")
    await h.registry.discover_and_load_all()

    await h.registry.stop_all()

    for snap in h.registry.snapshot():
        assert snap.state == PluginState.DISABLED.value
