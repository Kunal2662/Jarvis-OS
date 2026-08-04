"""Unit tests for ``jarvis.core.plugins.manifest`` (Milestone 9 Task
Group D, Phase 1)."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from jarvis.core.plugins.manifest import (
    PluginManifest,
    PluginManifestError,
    load_manifest,
)

_MINIMAL = {
    "name": "hello-world",
    "display_name": "Hello World",
    "version": "1.0.0",
    "entry_point": "plugin:HelloWorldPlugin",
}


def test_minimal_manifest_applies_defaults():
    manifest = PluginManifest.model_validate(_MINIMAL)
    assert manifest.plugin_id == "hello-world"
    assert manifest.permissions == []
    assert set(manifest.supported_os) == {"windows", "linux", "macos"}
    assert manifest.min_jarvis_version == "0.0.0"


def test_rejects_invalid_name():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "name": "Hello World"})


def test_rejects_unknown_permission():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "permissions": ["root_access"]})


def test_accepts_known_permissions():
    manifest = PluginManifest.model_validate(
        {**_MINIMAL, "permissions": ["network", "memory.read"]}
    )
    assert manifest.permissions == ["network", "memory.read"]


def test_rejects_self_dependency():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "dependencies": ["hello-world"]})


def test_rejects_unknown_supported_os():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "supported_os": ["amiga"]})


def test_rejects_empty_supported_os():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "supported_os": []})


def test_rejects_unknown_required_capability():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "required_capabilities": ["telepathy"]})


def test_accepts_known_required_capability():
    manifest = PluginManifest.model_validate(
        {**_MINIMAL, "required_capabilities": ["global_hotkey"]}
    )
    assert manifest.required_capabilities == ["global_hotkey"]


def test_rejects_invalid_version():
    with pytest.raises(ValidationError):
        PluginManifest.model_validate({**_MINIMAL, "version": "not-semver"})


def test_platform_specific_entry_point_dict():
    manifest = PluginManifest.model_validate(
        {**_MINIMAL, "entry_point": {"windows": "plugin_win:Plugin", "default": "plugin:Plugin"}}
    )
    assert manifest.entry_point == {"windows": "plugin_win:Plugin", "default": "plugin:Plugin"}


def test_config_schema_realized_from_settings_schema():
    manifest = PluginManifest.model_validate(
        {
            **_MINIMAL,
            "settings_schema": {
                "sync_interval_minutes": {"type": "integer", "default": 15},
            },
        }
    )
    schema = manifest.config_schema()
    assert schema.defaults() == {"sync_interval_minutes": 15}


def test_config_schema_rejects_malformed_field():
    manifest = PluginManifest.model_validate(
        {**_MINIMAL, "settings_schema": {"bad": "not-an-object"}}
    )
    with pytest.raises(PluginManifestError):
        manifest.config_schema()


def test_manifest_is_frozen():
    manifest = PluginManifest.model_validate(_MINIMAL)
    with pytest.raises(ValidationError):
        manifest.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# load_manifest() -- real filesystem round trip.
# ---------------------------------------------------------------------------
def test_load_manifest_round_trip(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_MINIMAL), encoding="utf-8")
    manifest = load_manifest(manifest_path)
    assert manifest.name == "hello-world"


def test_load_manifest_missing_file(tmp_path):
    with pytest.raises(PluginManifestError):
        load_manifest(tmp_path / "does-not-exist.json")


def test_load_manifest_invalid_json(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(PluginManifestError):
        load_manifest(manifest_path)


def test_load_manifest_schema_invalid(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"name": "x"}), encoding="utf-8")
    with pytest.raises(PluginManifestError):
        load_manifest(manifest_path)
