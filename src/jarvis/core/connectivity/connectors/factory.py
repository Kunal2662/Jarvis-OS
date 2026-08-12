"""Connector factory -- Milestone 12 Task Group B, Phases 2-3.

Builds a concrete `IDeviceConnector` from plain configuration and
registers every shipped connector into Phase 1's
`ConnectorFactoryRegistry`. Directly mirrors `core/mcp/transports/
factory.py` -- same reasoning: a plain callable per connector type, one
creation path, nothing above this layer branches on connector type.

Phase 3 adds `build_mqtt_connector` alongside Phase 2's own Home
Assistant factory -- exactly the "adding MQTT later means adding one
factory here and nothing else" this module's own Phase 2 docstring
predicted.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.connectivity.connectors.home_assistant import HomeAssistantConnector
from jarvis.core.connectivity.connectors.mqtt import MqttConnector
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.interfaces.connectivity import ConnectivityError

if TYPE_CHECKING:
    from jarvis.core.interfaces.connectivity import IDeviceConnector


def _require(config: dict[str, Any], key: str, connector_type: str) -> Any:
    value = config.get(key)
    if value in (None, ""):
        raise ConnectivityError(
            f"{connector_type} connector requires a {key!r} entry in its configuration."
        )
    return value


def build_home_assistant_connector(config: dict[str, Any]) -> IDeviceConnector:
    return HomeAssistantConnector(
        str(_require(config, "base_url", "home_assistant")),
        str(_require(config, "token", "home_assistant")),
        verify=bool(config.get("verify", True)),
        **_timeout_kwargs(config),
    )


def _timeout_kwargs(config: dict[str, Any]) -> dict[str, float]:
    timeout = config.get("request_timeout_seconds")
    return {} if timeout is None else {"request_timeout_seconds": float(timeout)}


#: Every optional `MqttConnector.__init__` keyword this factory passes
#: through, and the caster each one's config value is coerced with.
#: Table-driven rather than one ``if "x" in config`` branch per key --
#: the two are equivalent, but the branch-per-key form trips this
#: project's own complexity gate past a fixed number of keys.
_MQTT_OPTIONAL_CONFIG: dict[str, type] = {
    "port": int,
    "client_id": str,
    "username": str,
    "password": str,
    "use_tls": bool,
    "verify": bool,
    "discovery_prefix": str,
    "native_prefix": str,
    "keepalive_seconds": int,
    "discovery_window_seconds": float,
    "reconnect_delay_seconds": float,
    "connect_timeout_seconds": float,
}


def build_mqtt_connector(config: dict[str, Any]) -> IDeviceConnector:
    """Only ``host`` is required -- every other key mirrors
    `MqttConnector.__init__`'s own defaults, so an operator configuring
    a plain local broker supplies nothing beyond a host."""
    kwargs = {
        key: caster(config[key]) for key, caster in _MQTT_OPTIONAL_CONFIG.items() if key in config
    }
    return MqttConnector(str(_require(config, "host", "mqtt")), **kwargs)


def build_default_connector_registry() -> ConnectorFactoryRegistry:
    """Every connector this build ships, registered.

    Phase 1 left this registry deliberately empty and documented that a
    later pass would populate it at the DI composition root. Phase 2
    was that call for Home Assistant; this is that call for MQTT.
    """
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", build_home_assistant_connector)
    registry.register("mqtt", build_mqtt_connector)
    return registry
