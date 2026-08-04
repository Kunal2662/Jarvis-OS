"""End-to-end Plugin Platform test (Milestone 9 Task Group D) -- the
real Loader + Sandbox + Permission Model + Registry stack, no mock of
any of them, loading the real ``tests/fixtures/plugins/hello_world``
plugin from disk.

Proves the roadmap's own Plugin Platform acceptance criterion
(``docs/MASTER_ROADMAP.md`` section 8 M9): *"A hello-world plugin
registers a slash command and a hotkey."* Also exercises the full
least-privilege permission workflow end to end -- declare -> denied
while pending -> grant -> now allowed -- rather than starting from an
already-granted state.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.plugins.loader import PluginLoader
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.core.plugins.registry import PluginRegistry, PluginState
from jarvis.core.plugins.sandbox import PluginSandbox

_FIXTURE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "plugins" / "hello_world"


class _FakePlatformAdapter:
    """A real ``IPlatformAdapter`` shape, fixed to report "everywhere
    supported" so this test exercises the plugin platform itself, not
    this specific machine's real OS/arch match."""

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


class _FakeHotkeyService:
    """Stands in for the real ``services/hotkey_service.py`` --
    exercising the exact ``register(semantic, combo, callback)``/
    ``unregister(semantic)`` contract :class:`PluginHotkeys` calls
    against the real service in production."""

    def __init__(self) -> None:
        self.registered: dict[str, tuple[str, object]] = {}

    def register(self, semantic, combo, callback) -> None:
        self.registered[semantic] = (combo, callback)

    def unregister(self, semantic) -> None:
        self.registered.pop(semantic, None)


@pytest.mark.asyncio
async def test_hello_world_plugin_registers_command_and_hotkey_end_to_end(tmp_path):
    # ---- Arrange: stage the real fixture into a plugins_dir under its
    # manifest-declared name (the Loader requires the folder name and
    # manifest ``name`` to match) -- the same "install into the right
    # folder" step PluginStore/PluginRegistry.install() do for real.
    plugins_dir = tmp_path / "plugins"
    plugins_dir.mkdir()
    shutil.copytree(_FIXTURE_DIR, plugins_dir / "hello-world")

    event_bus = EventBus()
    loader = PluginLoader(
        plugins_dir, platform_adapter=_FakePlatformAdapter(), app_version="0.10.0"
    )
    sandbox = PluginSandbox()
    permission_model = PermissionModel(event_bus, store_path=tmp_path / "permissions.json")
    hotkey_service = _FakeHotkeyService()
    registry = PluginRegistry(
        loader=loader,
        sandbox=sandbox,
        permission_model=permission_model,
        event_bus=event_bus,
        platform_adapter=_FakePlatformAdapter(),
        plugin_data_root=tmp_path / "plugin-data",
        hotkey_service=hotkey_service,
    )

    # ---- Act 1: first boot, permission not yet granted -- least-
    # privilege default means on_load's hotkey registration fails, and
    # the whole plugin is correctly reported FAILED, not silently
    # half-working.
    await registry.discover_and_load_all()
    assert registry.status("hello-world").state == PluginState.FAILED.value
    assert not permission_model.is_granted("hello-world", "hotkey")
    assert ("hello-world", "hotkey") in permission_model.pending()

    # ---- Act 2: grant the permission (the real approval workflow a
    # future Developer Mode UI would trigger) and enable the plugin.
    await permission_model.grant("hello-world", "hotkey")
    enabled = await registry.enable("hello-world")

    # ---- Assert: plugin is genuinely running, with both a registered
    # slash command AND a registered hotkey -- the acceptance criterion.
    assert enabled is True
    assert registry.status("hello-world").state == PluginState.RUNNING.value

    context = registry.get_context("hello-world")
    assert context is not None
    assert "hello.greet" in context.commands.registered_ids
    assert "plugin.hello-world.greet" in hotkey_service.registered
    combo, callback = hotkey_service.registered["plugin.hello-world.greet"]
    assert combo == "ctrl+alt+h"

    # ---- The command actually runs, reading the plugin's own config.
    result = await context.commands.invoke("hello.greet")
    assert result == "Hello, world!"
    result = await context.commands.invoke("hello.greet", who="JARVIS")
    assert result == "Hello, JARVIS!"

    # ---- The hotkey callback actually runs.
    callback()
    assert registry.snapshot()  # sanity: registry still tracks the plugin

    # ---- Act 3: disable -- the hotkey must not be left orphaned
    # (Plugin Safe Core Architecture's "no orphan hooks" requirement).
    disabled = await registry.disable("hello-world")
    assert disabled is True
    assert registry.status("hello-world").state == PluginState.DISABLED.value
    assert hotkey_service.registered == {}
