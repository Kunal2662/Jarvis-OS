"""Unit tests for ``jarvis.core.plugins.sdk`` (Milestone 9 Task Group D,
Phase 1)."""

from __future__ import annotations

import pytest

from jarvis.core.plugins.sdk import (
    PERMISSION_SCOPES,
    IPermissionChecker,
    IPlugin,
    PluginConfigField,
    PluginConfigSchema,
    PluginError,
    is_valid_plugin_name,
    parse_semver,
    version_in_range,
)


class _RealPlugin:
    async def on_load(self, context) -> None: ...
    async def on_start(self) -> None: ...
    async def on_stop(self) -> None: ...


class _NotAPlugin:
    pass


def test_iplugin_protocol_structural_check():
    assert isinstance(_RealPlugin(), IPlugin)
    assert not isinstance(_NotAPlugin(), IPlugin)


class _AllowAllChecker:
    def is_granted(self, plugin_id: str, scope: str) -> bool:
        return True


def test_ipermission_checker_protocol():
    assert isinstance(_AllowAllChecker(), IPermissionChecker)


def test_permission_scopes_fixed_vocabulary():
    assert "network" in PERMISSION_SCOPES
    assert "memory.read" in PERMISSION_SCOPES
    assert len(PERMISSION_SCOPES) == 10


@pytest.mark.parametrize(
    "version,expected",
    [
        ("1.0.0", (1, 0, 0)),
        ("2.10.3", (2, 10, 3)),
        ("1.0.0-beta", (1, 0, 0)),
        ("1.0.0+build.5", (1, 0, 0)),
    ],
)
def test_parse_semver(version, expected):
    assert parse_semver(version) == expected


def test_parse_semver_rejects_garbage():
    with pytest.raises(PluginError):
        parse_semver("not-a-version")


@pytest.mark.parametrize(
    "version,range_spec,expected",
    [
        ("1.5.0", ">=1.0.0,<2.0.0", True),
        ("2.0.0", ">=1.0.0,<2.0.0", False),
        ("0.9.9", ">=1.0.0,<2.0.0", False),
        ("1.0.0", ">=1.0.0,<2.0.0", True),
        ("1.0.0", "", True),
        ("1.0.0", "==1.0.0", True),
        ("1.0.1", "==1.0.0", False),
        ("3.0.0", ">2.0.0", True),
        ("2.0.0", ">2.0.0", False),
        ("1.0.0", "<=1.0.0", True),
    ],
)
def test_version_in_range(version, range_spec, expected):
    assert version_in_range(version, range_spec) is expected


def test_version_in_range_rejects_malformed_clause():
    with pytest.raises(PluginError):
        version_in_range("1.0.0", "~=1.0.0")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("weather-widget", True),
        ("weather_widget", True),
        ("weather123", True),
        ("Weather", False),
        ("1weather", False),
        ("", False),
        ("weather widget", False),
    ],
)
def test_is_valid_plugin_name(name, expected):
    assert is_valid_plugin_name(name) is expected


def test_config_schema_fills_defaults():
    schema = PluginConfigSchema(
        fields={
            "sync_interval_minutes": PluginConfigField(type="integer", default=15),
            "enabled": PluginConfigField(type="boolean", default=True),
        }
    )
    assert schema.validate({}) == {"sync_interval_minutes": 15, "enabled": True}


def test_config_schema_overrides_and_drops_unknown_keys():
    schema = PluginConfigSchema(fields={"limit": PluginConfigField(type="integer", default=10)})
    result = schema.validate({"limit": 50, "unrelated": "ignored"})
    assert result == {"limit": 50}


def test_config_schema_wrong_type_raises():
    schema = PluginConfigSchema(fields={"limit": PluginConfigField(type="integer", default=10)})
    with pytest.raises(PluginError):
        schema.validate({"limit": "fifty"})


def test_config_schema_missing_required_raises():
    schema = PluginConfigSchema(fields={"api_key": PluginConfigField(type="string", required=True)})
    with pytest.raises(PluginError):
        schema.validate({})


def test_config_schema_required_field_present_ok():
    schema = PluginConfigSchema(fields={"api_key": PluginConfigField(type="string", required=True)})
    assert schema.validate({"api_key": "abc"}) == {"api_key": "abc"}
