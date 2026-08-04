"""Provider metadata and configuration tests -- Milestone 10.5 Task
Group C, deliverables 4 and 5."""

from __future__ import annotations

import pytest

from jarvis.core.mcp.negotiation import SUPPORTED_PROTOCOL_VERSIONS
from jarvis.core.mcp.providers.metadata import (
    PROVIDER_ACTIONS,
    HeartbeatSettings,
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
    ReconnectPolicy,
    RetryPolicy,
)

# --- Metadata ------------------------------------------------------------------


def test_metadata_defaults_are_usable() -> None:
    metadata = ProviderMetadata(name="demo")
    metadata.validate()

    assert metadata.version == "1.0.0"
    assert metadata.transport == "stdio"
    assert metadata.supported_protocols == SUPPORTED_PROTOCOL_VERSIONS


def test_metadata_rejects_an_empty_name() -> None:
    with pytest.raises(MCPProviderError, match="must not be empty"):
        ProviderMetadata(name="   ").validate()


def test_metadata_rejects_an_unknown_transport() -> None:
    with pytest.raises(MCPProviderError, match="unknown transport"):
        ProviderMetadata(name="demo", transport="carrier_pigeon").validate()


def test_metadata_rejects_a_permission_outside_the_existing_vocabulary() -> None:
    """Task Group C introduces no new permission vocabulary -- a
    provider may only request scopes the plugin platform defines."""
    with pytest.raises(MCPProviderError, match="unknown permission scope"):
        ProviderMetadata(name="demo", required_permissions=("mcp.invent_a_scope",)).validate()


def test_metadata_accepts_existing_permission_scopes() -> None:
    ProviderMetadata(name="demo", required_permissions=("agent_tools", "memory.read")).validate()


def test_metadata_rejects_an_empty_protocol_list() -> None:
    with pytest.raises(MCPProviderError, match="no supported protocol"):
        ProviderMetadata(name="demo", supported_protocols=()).validate()


def test_metadata_as_dict_is_complete_and_serializable() -> None:
    payload = ProviderMetadata(
        name="demo",
        version="2.0.0",
        author="someone",
        description="d",
        capabilities=("echo",),
        transport="http",
        required_permissions=("network",),
        tags=("t",),
    ).as_dict()

    assert payload["name"] == "demo"
    assert payload["capabilities"] == ["echo"]
    assert payload["required_permissions"] == ["network"]
    assert payload["tags"] == ["t"]


def test_metadata_is_frozen() -> None:
    metadata = ProviderMetadata(name="demo")
    with pytest.raises(Exception):  # noqa: B017 -- dataclass raises FrozenInstanceError
        metadata.name = "other"  # type: ignore[misc]


# --- Config --------------------------------------------------------------------


def test_config_defaults_validate() -> None:
    ProviderConfig().validate()


def test_config_transport_overrides_metadata() -> None:
    """Deployment-time transport choice must win over the provider's
    own declared default, so an install can move stdio -> websocket
    without editing the provider."""
    metadata = ProviderMetadata(name="demo", transport="stdio")

    assert ProviderConfig().resolved_transport(metadata) == "stdio"
    assert ProviderConfig(transport="websocket").resolved_transport(metadata) == "websocket"


def test_config_rejects_an_unknown_transport() -> None:
    with pytest.raises(MCPProviderError, match="unknown transport"):
        ProviderConfig(transport="carrier_pigeon").validate()


@pytest.mark.parametrize(
    "config",
    [
        ProviderConfig(reconnect=ReconnectPolicy(max_attempts=0)),
        ProviderConfig(retry=RetryPolicy(max_attempts=0)),
    ],
)
def test_config_rejects_a_zero_attempt_policy(config: ProviderConfig) -> None:
    with pytest.raises(MCPProviderError, match="at least 1"):
        config.validate()


def test_config_as_dict_reports_option_keys_never_values() -> None:
    """Option values will carry credentials once M11's providers exist,
    so the reporting surface exposes key names only."""
    payload = ProviderConfig(options={"token": "super-secret", "url": "http://x"}).as_dict()

    assert payload["option_keys"] == ["token", "url"]
    assert "super-secret" not in str(payload)


def test_config_as_dict_includes_every_policy() -> None:
    payload = ProviderConfig(
        reconnect=ReconnectPolicy(max_attempts=5),
        retry=RetryPolicy(enabled=True, max_attempts=3),
        heartbeat=HeartbeatSettings(enabled=False, interval_seconds=12.0),
    ).as_dict()

    assert payload["reconnect"]["max_attempts"] == 5
    assert payload["retry"]["enabled"] is True
    assert payload["heartbeat"]["interval_seconds"] == 12.0


def test_heartbeat_zero_interval_means_use_the_global_setting() -> None:
    """Opting out is ``enabled=False``; a zero interval defers to the
    global cadence. Keeping them distinct means the two intents cannot
    be confused."""
    settings = HeartbeatSettings()

    assert settings.enabled is True
    assert settings.interval_seconds == 0.0


# --- State / action vocabulary --------------------------------------------------


def test_provider_actions_cover_every_documented_transition() -> None:
    assert {
        "registered",
        "initialized",
        "connected",
        "disconnected",
        "suspended",
        "resumed",
        "failed",
        "removed",
    } == PROVIDER_ACTIONS


def test_resumed_is_an_action_but_not_a_resting_state() -> None:
    """Resuming lands in CONNECTED; a RESUMED state would be one
    nothing ever rests in."""
    assert "resumed" in PROVIDER_ACTIONS
    assert "resumed" not in {s.value for s in ProviderState}
    assert ProviderState.CONNECTED.value == "connected"
