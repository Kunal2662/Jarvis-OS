"""Connector factory -- Milestone 12 Task Group B, Phase 2.

Builds a concrete `IDeviceConnector` from plain configuration and
registers every shipped connector into Phase 1's
`ConnectorFactoryRegistry`. Directly mirrors `core/mcp/transports/
factory.py` -- same reasoning: a plain callable per connector type, one
creation path, nothing above this layer branches on connector type.

`mqtt` is `CONNECTOR_TYPES`' other approved name, but Phase 3 (its own
later, separately-approved pass) is what registers it. Nothing here
does -- `ConnectorFactoryRegistry.create("mqtt", ...)` correctly
raising `ConnectorRegistrationError` today is the honest state, not a
gap this phase should paper over.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.connectivity.connectors.home_assistant import HomeAssistantConnector
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


def build_default_connector_registry() -> ConnectorFactoryRegistry:
    """Every connector this build ships, registered.

    Phase 1 left this registry deliberately empty and documented that a
    later pass would populate it at the DI composition root -- this is
    that call for Home Assistant. Adding MQTT later means adding one
    factory here and nothing else.
    """
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", build_home_assistant_connector)
    return registry
