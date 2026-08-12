"""Connector factory registry tests -- Milestone 12 Task Group B, Phase 1.

Mirrors ``test_mcp_transport_factory.py``'s registry-discovery half --
``ConnectorFactoryRegistry`` is deliberately the same shape as
``TransportFactoryRegistry``, minus the ``describe``/``discover``
surface MCP's registry adds (no connector is registered by default
here, so there is nothing yet to describe).
"""

from __future__ import annotations

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry, ConnectorRegistrationError
from jarvis.core.interfaces.connectivity import CONNECTOR_TYPES
from tests.fakes.fake_device_connector import FakeDeviceConnector


@pytest.fixture
def registry() -> ConnectorFactoryRegistry:
    return ConnectorFactoryRegistry()


def _factory(config: dict) -> FakeDeviceConnector:
    return FakeDeviceConnector()


def test_starts_empty(registry: ConnectorFactoryRegistry) -> None:
    assert registry.registered_types == ()
    assert registry.supports("home_assistant") is False


def test_register_then_create(registry: ConnectorFactoryRegistry) -> None:
    registry.register("home_assistant", _factory)

    assert registry.supports("home_assistant") is True
    assert registry.registered_types == ("home_assistant",)
    connector = registry.create("home_assistant", {})
    assert isinstance(connector, FakeDeviceConnector)


def test_registering_an_unknown_type_is_rejected(registry: ConnectorFactoryRegistry) -> None:
    with pytest.raises(ConnectorRegistrationError, match="Unknown connector type"):
        registry.register("zigbee", _factory)


def test_creating_an_unregistered_type_is_rejected(registry: ConnectorFactoryRegistry) -> None:
    with pytest.raises(ConnectorRegistrationError, match="No connector registered"):
        registry.create("mqtt", {})


def test_unregister_reports_whether_it_existed(registry: ConnectorFactoryRegistry) -> None:
    registry.register("mqtt", _factory)

    assert registry.unregister("mqtt") is True
    assert registry.unregister("mqtt") is False
    assert registry.supports("mqtt") is False


def test_create_defaults_to_an_empty_config(registry: ConnectorFactoryRegistry) -> None:
    seen: dict = {}

    def factory(config: dict) -> FakeDeviceConnector:
        seen.update(config)
        return FakeDeviceConnector()

    registry.register("home_assistant", factory)
    registry.create("home_assistant", None)

    assert seen == {}


def test_connector_types_is_the_task_group_bs_approved_scope() -> None:
    """Deliberately narrow -- BLE/Matter/Thread/Zigbee/Z-Wave are named
    in the roadmap's Future Expansion note but not approved for this
    task group."""
    assert frozenset({"home_assistant", "mqtt"}) == CONNECTOR_TYPES
