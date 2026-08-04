"""Unit tests for ``jarvis.core.plugins.extension_api`` (Milestone 9
Task Group D, Phase 4)."""

from __future__ import annotations

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import PluginCustomEvent, PluginNotificationEvent
from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.plugins.extension_api import (
    PluginCommandError,
    PluginFilesystemError,
    PluginHotkeyError,
    PluginPermissionError,
    PluginPermissions,
    build_plugin_context,
)
from jarvis.core.plugins.manifest import PluginManifest


class _AllowAllChecker:
    def is_granted(self, plugin_id: str, scope: str) -> bool:
        return True


class _DenyAllChecker:
    def is_granted(self, plugin_id: str, scope: str) -> bool:
        return False


class _FakePlatformAdapter:
    def info(self) -> PlatformInfo:
        return PlatformInfo(
            family=PlatformFamily.WINDOWS,
            os_release="test",
            architecture="x86_64",
            python_version="3.13.0",
        )

    def has_capability(self, capability: str) -> bool:
        return capability == "global_hotkey"

    def resolve_entry_point(self, entry_point, *, default_key="default"):
        return entry_point if isinstance(entry_point, str) else entry_point.get(default_key)


def _manifest(**overrides):
    data = {
        "name": "hello-world",
        "display_name": "Hello World",
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
        "commands": [{"id": "hello.greet", "description": "Say hi"}],
        **overrides,
    }
    return PluginManifest.model_validate(data)


def _context(tmp_path, *, checker=None, manifest=None):
    return build_plugin_context(
        manifest or _manifest(),
        event_bus=EventBus(),
        permission_checker=checker or _AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "plugin-data",
    )


# ---- Permissions --------------------------------------------------------------
def test_permissions_allow_all():
    perms = PluginPermissions("p", _AllowAllChecker())
    assert perms.has("network") is True
    perms.require("network")  # does not raise


def test_permissions_deny_all_raises_on_require():
    perms = PluginPermissions("p", _DenyAllChecker())
    assert perms.has("network") is False
    with pytest.raises(PluginPermissionError):
        perms.require("network")


# ---- Events ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_event_channel_publish_wraps_in_plugin_custom_event(tmp_path):
    bus = EventBus()
    received = []
    bus.subscribe(PluginCustomEvent, received.append)
    context = build_plugin_context(
        _manifest(),
        event_bus=bus,
        permission_checker=_AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
    )
    await context.events.publish("greeted", {"who": "world"})
    assert len(received) == 1
    assert received[0].plugin_id == "hello-world"
    assert received[0].name == "greeted"
    assert received[0].payload == {"who": "world"}


@pytest.mark.asyncio
async def test_event_channel_subscribe_and_unsubscribe(tmp_path):
    bus = EventBus()
    context = build_plugin_context(
        _manifest(),
        event_bus=bus,
        permission_checker=_AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
    )
    calls = []

    async def handler(event):
        calls.append(event)

    unsubscribe = context.events.subscribe(PluginNotificationEvent, handler)
    await bus.publish(PluginNotificationEvent(plugin_id="x", title="t", message="m"))
    assert len(calls) == 1

    unsubscribe()
    await bus.publish(PluginNotificationEvent(plugin_id="x", title="t2", message="m2"))
    assert len(calls) == 1


# ---- Commands ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commands_register_and_invoke_declared_command(tmp_path):
    context = _context(tmp_path)
    calls = []

    async def handler(**kwargs):
        calls.append(kwargs)
        return "ok"

    context.commands.register("hello.greet", handler)
    result = await context.commands.invoke("hello.greet", who="world")
    assert result == "ok"
    assert calls == [{"who": "world"}]


def test_commands_register_undeclared_id_raises(tmp_path):
    context = _context(tmp_path)
    with pytest.raises(PluginCommandError):
        context.commands.register("not.declared", lambda **kw: None)


@pytest.mark.asyncio
async def test_commands_invoke_unregistered_raises(tmp_path):
    context = _context(tmp_path)
    with pytest.raises(PluginCommandError):
        await context.commands.invoke("hello.greet")


# ---- Filesystem ---------------------------------------------------------------------
def test_filesystem_write_and_read_round_trip(tmp_path):
    context = _context(tmp_path)
    context.filesystem.write_text("notes/todo.txt", "buy milk")
    assert context.filesystem.read_text("notes/todo.txt") == "buy milk"
    assert "notes" in context.filesystem.list_dir(".")


def test_filesystem_denies_without_permission(tmp_path):
    context = _context(tmp_path, checker=_DenyAllChecker())
    with pytest.raises(PluginPermissionError):
        context.filesystem.write_text("x.txt", "data")


def test_filesystem_blocks_path_traversal(tmp_path):
    context = _context(tmp_path)
    with pytest.raises(PluginFilesystemError):
        context.filesystem.read_text("../../outside.txt")


def test_filesystem_read_missing_file_raises(tmp_path):
    context = _context(tmp_path)
    with pytest.raises(PluginFilesystemError):
        context.filesystem.read_text("does-not-exist.txt")


# ---- Network ---------------------------------------------------------------------
def test_network_is_allowed_reflects_permission(tmp_path):
    allowed = _context(tmp_path, checker=_AllowAllChecker())
    denied = _context(tmp_path, checker=_DenyAllChecker())
    assert allowed.network.is_allowed is True
    assert denied.network.is_allowed is False


# ---- Hotkeys ---------------------------------------------------------------------
class _FakeHotkeyService:
    def __init__(self) -> None:
        self.registered: dict[str, tuple[str, object]] = {}

    def register(self, semantic, combo, callback) -> None:
        self.registered[semantic] = (combo, callback)

    def unregister(self, semantic) -> None:
        self.registered.pop(semantic, None)


def test_hotkeys_register_requires_permission(tmp_path):
    context = build_plugin_context(
        _manifest(),
        event_bus=EventBus(),
        permission_checker=_DenyAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
        hotkey_service=_FakeHotkeyService(),
    )
    with pytest.raises(PluginPermissionError):
        context.hotkeys.register("greet", "ctrl+alt+g", lambda: None)


def test_hotkeys_register_without_service_raises(tmp_path):
    context = _context(tmp_path)  # no hotkey_service passed -> None
    with pytest.raises(PluginHotkeyError):
        context.hotkeys.register("greet", "ctrl+alt+g", lambda: None)


def test_hotkeys_register_namespaces_and_delegates(tmp_path):
    service = _FakeHotkeyService()
    context = build_plugin_context(
        _manifest(),
        event_bus=EventBus(),
        permission_checker=_AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
        hotkey_service=service,
    )
    callback = lambda: None  # noqa: E731

    context.hotkeys.register("greet", "ctrl+alt+g", callback)

    assert "plugin.hello-world.greet" in service.registered
    assert service.registered["plugin.hello-world.greet"] == ("ctrl+alt+g", callback)
    assert context.hotkeys.registered_semantics == frozenset({"plugin.hello-world.greet"})


def test_hotkeys_unregister_all_clears_service(tmp_path):
    service = _FakeHotkeyService()
    context = build_plugin_context(
        _manifest(),
        event_bus=EventBus(),
        permission_checker=_AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
        hotkey_service=service,
    )
    context.hotkeys.register("greet", "ctrl+alt+g", lambda: None)

    context.hotkeys.unregister_all()

    assert service.registered == {}
    assert context.hotkeys.registered_semantics == frozenset()


def test_hotkeys_unregister_all_without_service_is_noop(tmp_path):
    context = _context(tmp_path)
    context.hotkeys.unregister_all()  # does not raise


# ---- Notifications ---------------------------------------------------------------------
@pytest.mark.asyncio
async def test_notifications_publish_requires_permission(tmp_path):
    context = _context(tmp_path, checker=_DenyAllChecker())
    with pytest.raises(PluginPermissionError):
        await context.notifications.publish("Title", "Message")


@pytest.mark.asyncio
async def test_notifications_publish_real_event(tmp_path):
    bus = EventBus()
    received = []
    bus.subscribe(PluginNotificationEvent, received.append)
    context = build_plugin_context(
        _manifest(),
        event_bus=bus,
        permission_checker=_AllowAllChecker(),
        platform_adapter=_FakePlatformAdapter(),
        data_dir=tmp_path / "data",
    )
    await context.notifications.publish("Title", "Message")
    assert len(received) == 1
    assert received[0].title == "Title"


# ---- Platform ---------------------------------------------------------------------
def test_platform_info_reflects_adapter(tmp_path):
    context = _context(tmp_path)
    assert context.platform.os_family == "windows"
    assert context.platform.architecture == "x86_64"
    assert context.platform.has_capability("global_hotkey") is True
    assert context.platform.has_capability("gpu") is False


# ---- Config ---------------------------------------------------------------------
def test_config_defaults_and_update(tmp_path):
    manifest = _manifest(
        settings_schema={"limit": {"type": "integer", "default": 10}},
    )
    context = _context(tmp_path, manifest=manifest)
    assert context.config.get_all() == {"limit": 10}
    assert context.config.get("limit") == 10
    updated = context.config.update({"limit": 50})
    assert updated == {"limit": 50}
    assert context.config.get("limit") == 50


# ---- Manifest (UI extension points query surface) ------------------------------------
def test_manifest_exposes_declared_ui_surface(tmp_path):
    context = _context(tmp_path)
    assert context.manifest.commands[0].id == "hello.greet"
    assert context.plugin_id == "hello-world"
