"""Unit tests for the Platform Abstraction Layer (Milestone 9 Task
Group D, Universal Compatibility): ``core.interfaces.platform`` +
``infrastructure.platform.adapter.DefaultPlatformAdapter``."""

from __future__ import annotations

import pytest

from jarvis.core.interfaces.platform import CAPABILITY_VOCABULARY, IPlatformAdapter, PlatformFamily
from jarvis.infrastructure.platform.adapter import DefaultPlatformAdapter


def _adapter() -> DefaultPlatformAdapter:
    return DefaultPlatformAdapter()


def test_adapter_satisfies_protocol():
    assert isinstance(_adapter(), IPlatformAdapter)


def test_info_reports_a_real_known_family():
    info = _adapter().info()
    assert info.family in set(PlatformFamily)
    assert info.architecture
    assert info.python_version


def test_has_capability_unknown_name_is_false():
    assert _adapter().has_capability("teleportation") is False


@pytest.mark.parametrize("capability", sorted(CAPABILITY_VOCABULARY))
def test_has_capability_known_names_return_bool(capability):
    result = _adapter().has_capability(capability)
    assert isinstance(result, bool)


def test_resolve_entry_point_plain_string_passthrough():
    assert _adapter().resolve_entry_point("plugin:Plugin") == "plugin:Plugin"


def test_resolve_entry_point_platform_specific_wins():
    adapter = _adapter()
    family = adapter.info().family.value
    mapping = {family: "plugin_specific:Plugin", "default": "plugin_default:Plugin"}
    assert adapter.resolve_entry_point(mapping) == "plugin_specific:Plugin"


def test_resolve_entry_point_falls_back_to_default():
    adapter = _adapter()
    mapping = {"__no_such_platform__": "x:Y", "default": "plugin_default:Plugin"}
    assert adapter.resolve_entry_point(mapping) == "plugin_default:Plugin"


def test_resolve_entry_point_none_when_unsupported():
    adapter = _adapter()
    assert adapter.resolve_entry_point({"__no_such_platform__": "x:Y"}) is None
