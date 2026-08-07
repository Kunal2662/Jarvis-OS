"""Connector factory tests -- Milestone 12 Task Group B, Phase 2.

Mirrors ``test_mcp_transport_factory.py``'s registration half.
``ConnectorFactoryRegistry`` itself has no ``discover``/``describe``
surface (see ``test_connectivity_registry.py``'s own docstring for
why), so this file covers only what Phase 2 actually added: the
factory function and the populated default registry.
"""

from __future__ import annotations

import pytest

from jarvis.core.connectivity.connectors.factory import (
    build_default_connector_registry,
    build_home_assistant_connector,
)
from jarvis.core.interfaces.connectivity import ConnectivityError, IDeviceConnector


def test_only_home_assistant_is_registered() -> None:
    """Phase 2 ships the Home Assistant connector; ``mqtt`` stays
    unregistered until Phase 3's own separately-approved pass."""
    registry = build_default_connector_registry()

    assert registry.registered_types == ("home_assistant",)
    assert registry.supports("home_assistant") is True
    assert registry.supports("mqtt") is False


def test_factory_builds_a_connector_satisfying_the_port() -> None:
    registry = build_default_connector_registry()

    connector = registry.create(
        "home_assistant", {"base_url": "http://127.0.0.1:8123", "token": "t"}
    )

    assert isinstance(connector, IDeviceConnector)
    assert connector.connector_type == "home_assistant"
    assert connector.is_connected is False


def test_missing_base_url_fails_loudly() -> None:
    """A misconfigured connector must fail at construction with a
    message naming the key, not at first use with a confusing connect
    error -- the same discipline ``test_missing_required_config_fails_
    loudly`` enforces for MCP transports."""
    with pytest.raises(ConnectivityError, match="base_url"):
        build_home_assistant_connector({"token": "t"})


def test_missing_token_fails_loudly() -> None:
    with pytest.raises(ConnectivityError, match="token"):
        build_home_assistant_connector({"base_url": "http://127.0.0.1:8123"})


def test_request_timeout_is_configurable() -> None:
    connector = build_home_assistant_connector(
        {
            "base_url": "http://127.0.0.1:8123",
            "token": "t",
            "request_timeout_seconds": 2.5,
        }
    )
    assert connector._timeout == 2.5


def test_base_url_trailing_slash_is_normalized() -> None:
    connector = build_home_assistant_connector({"base_url": "http://127.0.0.1:8123/", "token": "t"})
    assert connector.base_url == "http://127.0.0.1:8123"
