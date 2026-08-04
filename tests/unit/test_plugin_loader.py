"""Unit tests for ``jarvis.core.plugins.loader`` (Milestone 9 Task
Group D, Phase 2)."""

from __future__ import annotations

import json
import sys
import textwrap

import pytest

from jarvis.core.interfaces.platform import PlatformFamily, PlatformInfo
from jarvis.core.plugins.loader import (
    DiscoveredPlugin,
    PluginLoader,
    PluginLoadError,
)
from jarvis.core.plugins.manifest import PluginManifest

_VALID_PLUGIN_PY = textwrap.dedent(
    """
    VALUE = 1

    class HelloPlugin:
        async def on_load(self, context) -> None:
            self.loaded = True

        async def on_start(self) -> None:
            pass

        async def on_stop(self) -> None:
            pass
    """
)

_NOT_A_PLUGIN_PY = "class NotAPlugin:\n    pass\n"


class _FakePlatformAdapter:
    def __init__(
        self,
        *,
        family: PlatformFamily = PlatformFamily.WINDOWS,
        architecture: str = "x86_64",
        capabilities: frozenset[str] = frozenset(),
    ) -> None:
        self._info = PlatformInfo(
            family=family, os_release="test", architecture=architecture, python_version="3.13.0"
        )
        self._capabilities = capabilities

    def info(self) -> PlatformInfo:
        return self._info

    def has_capability(self, capability: str) -> bool:
        return capability in self._capabilities

    def resolve_entry_point(self, entry_point, *, default_key: str = "default"):
        if isinstance(entry_point, str):
            return entry_point
        family = self._info.family.value
        return entry_point.get(family, entry_point.get(default_key))


def _write_plugin(
    root, plugin_id, *, manifest_overrides=None, code=_VALID_PLUGIN_PY, module="plugin"
):
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_id,
        "display_name": plugin_id.title(),
        "version": "1.0.0",
        "entry_point": f"{module}:HelloPlugin",
        **(manifest_overrides or {}),
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / f"{module}.py").write_text(code, encoding="utf-8")
    return plugin_dir


def _loader(plugins_dir, *, adapter=None, app_version="0.10.0"):
    return PluginLoader(
        plugins_dir, platform_adapter=adapter or _FakePlatformAdapter(), app_version=app_version
    )


# ---- Discovery --------------------------------------------------------------
def test_discover_empty_dir_returns_empty(tmp_path):
    loader = _loader(tmp_path / "does-not-exist")
    assert loader.discover() == ()


def test_discover_finds_valid_plugin(tmp_path):
    _write_plugin(tmp_path, "hello-world")
    loader = _loader(tmp_path)
    discovered = loader.discover()
    assert len(discovered) == 1
    assert discovered[0].plugin_id == "hello-world"


def test_discover_skips_invalid_manifest(tmp_path):
    _write_plugin(tmp_path, "good-plugin")
    bad_dir = tmp_path / "bad-plugin"
    bad_dir.mkdir()
    (bad_dir / "manifest.json").write_text("{not json", encoding="utf-8")
    loader = _loader(tmp_path)
    discovered = loader.discover()
    assert [d.plugin_id for d in discovered] == ["good-plugin"]


def test_discover_skips_name_mismatch(tmp_path):
    plugin_dir = tmp_path / "folder-name"
    plugin_dir.mkdir()
    manifest = {
        "name": "different-name",
        "display_name": "X",
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loader = _loader(tmp_path)
    assert loader.discover() == ()


def test_discover_skips_folder_with_no_manifest(tmp_path):
    (tmp_path / "not-a-plugin").mkdir()
    loader = _loader(tmp_path)
    assert loader.discover() == ()


# ---- Dependency resolution ---------------------------------------------------
def _discovered(plugin_id, dependencies=()):
    manifest = PluginManifest.model_validate(
        {
            "name": plugin_id,
            "display_name": plugin_id,
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "dependencies": list(dependencies),
        }
    )
    return DiscoveredPlugin(plugin_id=plugin_id, plugin_dir=None, manifest=manifest)  # type: ignore[arg-type]


def test_resolve_load_order_simple_chain(tmp_path):
    loader = _loader(tmp_path)
    result = loader.resolve_load_order((_discovered("a", ["b"]), _discovered("b")))
    assert result.order == ("b", "a")
    assert result.unresolved == {}


def test_resolve_load_order_missing_dependency_isolated(tmp_path):
    loader = _loader(tmp_path)
    result = loader.resolve_load_order((_discovered("a", ["ghost"]), _discovered("b")))
    assert result.order == ("b",)
    assert "a" in result.unresolved


def test_resolve_load_order_cycle_isolated(tmp_path):
    loader = _loader(tmp_path)
    result = loader.resolve_load_order(
        (_discovered("a", ["b"]), _discovered("b", ["a"]), _discovered("c"))
    )
    assert result.order == ("c",)
    assert set(result.unresolved) == {"a", "b"}


# ---- Compatibility ------------------------------------------------------------
def test_check_compatible_ok(tmp_path):
    loader = _loader(tmp_path)
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "supported_os": ["windows"],
            "supported_arch": ["x86_64"],
        }
    )
    ok, reason = loader.check_compatible(manifest)
    assert ok is True
    assert reason == ""


def test_check_compatible_wrong_os(tmp_path):
    loader = _loader(tmp_path)
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "supported_os": ["linux"],
        }
    )
    ok, reason = loader.check_compatible(manifest)
    assert ok is False
    assert "windows" in reason


def test_check_compatible_missing_capability(tmp_path):
    loader = _loader(tmp_path, adapter=_FakePlatformAdapter(capabilities=frozenset()))
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "required_capabilities": ["global_hotkey"],
        }
    )
    ok, reason = loader.check_compatible(manifest)
    assert ok is False
    assert "global_hotkey" in reason


def test_check_compatible_capability_present(tmp_path):
    loader = _loader(
        tmp_path, adapter=_FakePlatformAdapter(capabilities=frozenset({"global_hotkey"}))
    )
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "required_capabilities": ["global_hotkey"],
        }
    )
    ok, _ = loader.check_compatible(manifest)
    assert ok is True


def test_check_compatible_sdk_range_mismatch(tmp_path):
    loader = _loader(tmp_path)
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "sdk_range": ">=99.0.0",
        }
    )
    ok, reason = loader.check_compatible(manifest)
    assert ok is False
    assert "sdk_range" in reason


def test_check_compatible_app_too_old(tmp_path):
    loader = _loader(tmp_path, app_version="0.1.0")
    manifest = PluginManifest.model_validate(
        {
            "name": "x",
            "display_name": "X",
            "version": "1.0.0",
            "entry_point": "plugin:HelloPlugin",
            "min_jarvis_version": "5.0.0",
        }
    )
    ok, reason = loader.check_compatible(manifest)
    assert ok is False
    assert "min_jarvis_version" in reason


# ---- Import / unload / reload -------------------------------------------------
def test_import_plugin_success(tmp_path):
    _write_plugin(tmp_path, "hello-world")
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    instance = loader.import_plugin(discovered)
    assert instance.__class__.__name__ == "HelloPlugin"
    assert loader.is_loaded("hello-world")
    assert loader.get_instance("hello-world") is instance


def test_import_plugin_missing_entry_file(tmp_path):
    plugin_dir = tmp_path / "broken"
    plugin_dir.mkdir()
    manifest = {
        "name": "broken",
        "display_name": "Broken",
        "version": "1.0.0",
        "entry_point": "missing_module:HelloPlugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    with pytest.raises(PluginLoadError):
        loader.import_plugin(discovered)


def test_import_plugin_bad_entry_point_format(tmp_path):
    _write_plugin(tmp_path, "hello-world", manifest_overrides={"entry_point": "no-colon-here"})
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    with pytest.raises(PluginLoadError):
        loader.import_plugin(discovered)


def test_import_plugin_class_not_found(tmp_path):
    _write_plugin(tmp_path, "hello-world", manifest_overrides={"entry_point": "plugin:GhostClass"})
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    with pytest.raises(PluginLoadError):
        loader.import_plugin(discovered)


def test_import_plugin_not_iplugin(tmp_path):
    _write_plugin(
        tmp_path,
        "not-a-plugin",
        code=_NOT_A_PLUGIN_PY,
        manifest_overrides={"entry_point": "plugin:NotAPlugin"},
    )
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    with pytest.raises(PluginLoadError):
        loader.import_plugin(discovered)


def test_import_plugin_incompatible_raises(tmp_path):
    _write_plugin(tmp_path, "hello-world", manifest_overrides={"supported_os": ["linux"]})
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    with pytest.raises(PluginLoadError):
        loader.import_plugin(discovered)


def test_unload_removes_bookkeeping(tmp_path):
    _write_plugin(tmp_path, "hello-world")
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    loader.import_plugin(discovered)
    module_name = "_jarvis_plugin__hello_world"
    assert module_name in sys.modules
    loader.unload("hello-world")
    assert not loader.is_loaded("hello-world")
    assert module_name not in sys.modules


def test_reload_picks_up_code_change(tmp_path):
    plugin_dir = _write_plugin(tmp_path, "hello-world")
    loader = _loader(tmp_path)
    (discovered,) = loader.discover()
    loader.import_plugin(discovered)
    module_name = "_jarvis_plugin__hello_world"
    assert sys.modules[module_name].VALUE == 1

    (plugin_dir / "plugin.py").write_text(
        _VALID_PLUGIN_PY.replace("VALUE = 1", "VALUE = 2"), encoding="utf-8"
    )
    new_instance = loader.reload("hello-world")

    assert sys.modules[module_name].VALUE == 2
    assert loader.get_instance("hello-world") is new_instance


def test_reload_unloaded_plugin_raises(tmp_path):
    loader = _loader(tmp_path)
    with pytest.raises(PluginLoadError):
        loader.reload("never-loaded")
