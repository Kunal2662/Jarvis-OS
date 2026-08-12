"""Connector factory tests -- Milestone 12 Task Group B, Phases 2-3.

Mirrors ``test_mcp_transport_factory.py``'s registration half.
``ConnectorFactoryRegistry`` itself has no ``discover``/``describe``
surface (see ``test_connectivity_registry.py``'s own docstring for
why), so this file covers only what Phases 2 and 3 actually added: the
two factory functions and the populated default registry.
"""

from __future__ import annotations

import pytest

from jarvis.core.connectivity.connectors.factory import (
    build_default_connector_registry,
    build_home_assistant_connector,
    build_mqtt_connector,
)
from jarvis.core.interfaces.connectivity import ConnectivityError, IDeviceConnector


def test_both_shipped_connectors_are_registered() -> None:
    """Phase 2 shipped Home Assistant; Phase 3 shipped MQTT. Both are
    this task group's only two approved `CONNECTOR_TYPES` entries, and
    both are registered by the time this task group closes."""
    registry = build_default_connector_registry()

    assert registry.registered_types == ("home_assistant", "mqtt")
    assert registry.supports("home_assistant") is True
    assert registry.supports("mqtt") is True


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


# --- MQTT (Phase 3) ---------------------------------------------------------------


def test_mqtt_factory_builds_a_connector_satisfying_the_port() -> None:
    registry = build_default_connector_registry()

    connector = registry.create("mqtt", {"host": "127.0.0.1"})

    assert isinstance(connector, IDeviceConnector)
    assert connector.connector_type == "mqtt"
    assert connector.is_connected is False


def test_mqtt_missing_host_fails_loudly() -> None:
    with pytest.raises(ConnectivityError, match="host"):
        build_mqtt_connector({})


def test_mqtt_only_host_is_required() -> None:
    """Every other key mirrors `MqttConnector.__init__`'s own
    defaults -- an operator configuring a plain local broker supplies
    nothing beyond a host."""
    connector = build_mqtt_connector({"host": "127.0.0.1"})
    assert connector._port == 1883
    assert connector._use_tls is True


def test_mqtt_optional_config_is_coerced_and_passed_through() -> None:
    connector = build_mqtt_connector(
        {
            "host": "broker.local",
            "port": "8883",
            "client_id": "jarvis-1",
            "username": "jarvis",
            "password": "secret",
            "use_tls": False,
            "verify": False,
            "discovery_prefix": "custom_ha",
            "native_prefix": "custom_native",
            "keepalive_seconds": "30",
            "discovery_window_seconds": "1.5",
            "reconnect_delay_seconds": "2.5",
            "connect_timeout_seconds": "5",
        }
    )

    assert connector._host == "broker.local"
    assert connector._port == 8883
    assert connector._client_id == "jarvis-1"
    assert connector._username == "jarvis"
    assert connector._password == "secret"
    assert connector._use_tls is False
    assert connector._verify is False
    assert connector._discovery_prefix == "custom_ha"
    assert connector._native_prefix == "custom_native"
    assert connector._keepalive == 30
    assert connector._discovery_window == 1.5
    assert connector._reconnect_delay == 2.5
    assert connector._connect_timeout == 5.0
