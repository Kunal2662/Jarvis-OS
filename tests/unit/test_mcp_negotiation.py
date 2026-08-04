"""Unit tests for MCP capability negotiation -- Milestone 10.5 Task
Group A, deliverable 5. Pure functions, so every branch is reachable
without a connection or a permission store."""

from __future__ import annotations

from jarvis.core.interfaces.mcp import MCPCapability
from jarvis.core.mcp.negotiation import (
    PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
    HandshakeRequest,
    HandshakeResponse,
    negotiate,
    negotiate_version,
)

# --- Version compatibility ---------------------------------------------------


def test_picks_the_newest_shared_version() -> None:
    assert negotiate_version(("2025-06-18", "2025-03-26"), ("2025-03-26", "2025-06-18")) == (
        "2025-06-18"
    )


def test_falls_back_gracefully_to_an_older_shared_version() -> None:
    """A peer that only speaks the older revision still connects -- on
    that revision -- rather than being rejected."""
    assert negotiate_version(("2025-06-18", "2025-03-26"), ("2025-03-26",)) == "2025-03-26"


def test_no_shared_version_returns_none() -> None:
    assert negotiate_version(("2025-06-18",), ("1999-01-01",)) is None


def test_preference_order_wins_over_string_sorting() -> None:
    """ "Newest" follows the local preference list, not lexicographic
    order of date strings."""
    assert negotiate_version(("2025-03-26", "2025-06-18"), ("2025-06-18", "2025-03-26")) == (
        "2025-03-26"
    )


def test_protocol_version_is_the_first_supported() -> None:
    assert SUPPORTED_PROTOCOL_VERSIONS[0] == PROTOCOL_VERSION


# --- Full negotiation --------------------------------------------------------


def test_version_mismatch_fails_the_whole_negotiation() -> None:
    result = negotiate(
        [MCPCapability(name="echo")],
        remote_versions=["1999-01-01"],
        granted_scopes=set(),
    )

    assert result.succeeded is False
    assert result.agreed_version == ""
    assert "No shared protocol version" in result.failure_reason
    assert result.capabilities == ()


def test_capability_with_no_permissions_is_always_accepted() -> None:
    result = negotiate(
        [MCPCapability(name="ping", permissions=())],
        remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS),
        granted_scopes=set(),
    )

    assert result.succeeded is True
    assert result.capability_names == ("ping",)


def test_ungranted_capability_is_rejected_but_connection_still_succeeds() -> None:
    """Least-privilege: the ungranted capability drops out, the rest of
    the connection survives."""
    result = negotiate(
        [
            MCPCapability(name="allowed", permissions=("agent_tools",)),
            MCPCapability(name="blocked", permissions=("network",)),
        ],
        remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS),
        granted_scopes={"agent_tools"},
    )

    assert result.succeeded is True
    assert result.capability_names == ("allowed",)
    assert [name for name, _ in result.rejected] == ["blocked"]
    assert "network" in result.rejected[0][1]


def test_capability_needing_several_scopes_requires_all_of_them() -> None:
    offered = [MCPCapability(name="both", permissions=("agent_tools", "memory.read"))]

    partial = negotiate(
        offered,
        remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS),
        granted_scopes={"agent_tools"},
    )
    assert partial.capability_names == ()

    full = negotiate(
        offered,
        remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS),
        granted_scopes={"agent_tools", "memory.read"},
    )
    assert full.capability_names == ("both",)


def test_unknown_capability_kind_is_rejected_individually() -> None:
    result = negotiate(
        [
            MCPCapability(name="good", kind="tool"),
            MCPCapability(name="weird", kind="hologram"),
        ],
        remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS),
        granted_scopes=set(),
    )

    assert result.succeeded is True
    assert result.capability_names == ("good",)
    assert result.rejected[0][0] == "weird"
    assert "Unsupported capability kind" in result.rejected[0][1]


def test_empty_offer_negotiates_successfully_with_nothing() -> None:
    result = negotiate([], remote_versions=list(SUPPORTED_PROTOCOL_VERSIONS), granted_scopes=set())
    assert result.succeeded is True
    assert result.capabilities == ()


# --- Handshake value objects -------------------------------------------------


def test_handshake_request_defaults_to_supported_versions() -> None:
    assert HandshakeRequest(client_id="c").protocol_versions == SUPPORTED_PROTOCOL_VERSIONS


def test_handshake_response_success_is_derived_from_agreed_version() -> None:
    assert HandshakeResponse(server_id="s", agreed_version="2025-06-18").succeeded is True
    assert HandshakeResponse(server_id="s", failure_reason="nope").succeeded is False
