"""Validation framework tests -- Milestone 10.5 Task Group E,
deliverable 3.

The point of these validators is the *cross-object* check no single
model can make about itself, so the assertions here mostly build
individually-valid objects and prove the set is still wrong. Where a
check duplicates one the runtime model already performs, that is called
out rather than asserted twice.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.mcp import MCPCapability
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.auth.manager import MCPAuthManager
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry
from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata
from jarvis.core.mcp.providers.registry import MCPProviderRegistry
from jarvis.core.mcp.sdk.validation import (
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_auth,
    validate_capabilities,
    validate_capability,
    validate_provider_config,
    validate_provider_metadata,
    validate_registry_consistency,
    validate_transport_config,
)
from jarvis.core.mcp.transport import TransportFactoryRegistry
from jarvis.core.plugins.permissions import PermissionModel


def _codes(report: ValidationReport) -> set[str]:
    return {issue.code for issue in report.issues}


# --- Report shape ---------------------------------------------------------------


def test_report_separates_errors_from_warnings() -> None:
    """``ok`` ignores warnings on purpose: a warning describes something
    that *will* work, so treating it as a blocker would make developers
    silence it."""
    report = ValidationReport(
        issues=(
            ValidationIssue("a", "an error"),
            ValidationIssue("b", "a warning", severity=Severity.WARNING),
        )
    )

    assert report.ok is False  # an error is present, so not ok
    assert len(report.errors) == 1
    assert len(report.warnings) == 1


def test_report_merge_keeps_every_issue() -> None:
    left = ValidationReport(issues=(ValidationIssue("a", "x"),))
    right = ValidationReport(issues=(ValidationIssue("b", "y"),))

    assert _codes(left.merge(right)) == {"a", "b"}


def test_report_as_dict_is_json_safe() -> None:
    """The CLI and the REST layer both serialize this, so severity must
    already be a string rather than an enum."""
    payload = ValidationReport(
        issues=(ValidationIssue("a", "x", severity=Severity.WARNING, subject="s"),)
    ).as_dict()

    assert payload == {
        "ok": True,
        "error_count": 0,
        "warning_count": 1,
        "issues": [{"code": "a", "message": "x", "severity": "warning", "subject": "s"}],
    }


# --- Capability -----------------------------------------------------------------


def test_valid_capability_reports_nothing() -> None:
    capability = MCPCapability(
        name="demo.echo", kind="tool", description="Echoes.", permissions=("agent_tools",)
    )

    assert validate_capability(capability).issues == ()


def test_capability_unknown_kind_and_scope_are_errors() -> None:
    capability = MCPCapability(
        name="demo.echo", kind="widget", description="x", permissions=("teleport",)
    )

    assert _codes(validate_capability(capability)) == {
        "capability.unknown_kind",
        "capability.unknown_permission",
    }


def test_missing_description_is_a_warning_not_an_error() -> None:
    """An undescribed capability still works; it is just useless to an
    agent choosing between tools."""
    report = validate_capability(MCPCapability(name="demo.echo", kind="tool"))

    assert report.ok is True
    assert _codes(report) == {"capability.no_description"}


def test_duplicate_names_are_caught_across_a_batch() -> None:
    """The check a single capability cannot make about itself: a later
    registration shadows the earlier one, silently changing what an
    existing permission grant authorizes."""
    one = MCPCapability(name="demo.echo", kind="tool", description="first")
    two = MCPCapability(name="demo.echo", kind="tool", description="second")

    report = validate_capabilities([one, two])

    assert report.ok is False
    assert "capability.duplicate_name" in _codes(report)


def test_distinct_names_produce_no_duplicate_issue() -> None:
    one = MCPCapability(name="demo.echo", kind="tool", description="first")
    two = MCPCapability(name="demo.ping", kind="tool", description="second")

    assert "capability.duplicate_name" not in _codes(validate_capabilities([one, two]))


# --- Provider metadata ----------------------------------------------------------


def test_provider_with_no_common_protocol_is_an_error() -> None:
    """Independently valid -- the version strings are well-formed -- but
    negotiation against this build could never succeed."""
    metadata = ProviderMetadata(name="Demo", description="d", supported_protocols=("1999-01-01",))

    assert "provider.no_common_protocol" in _codes(validate_provider_metadata(metadata))


def test_provider_unknown_transport_is_an_error() -> None:
    metadata = ProviderMetadata(name="Demo", description="d", transport="carrier_pigeon")

    assert "provider.unknown_transport" in _codes(validate_provider_metadata(metadata))


def test_provider_missing_description_is_only_a_warning() -> None:
    report = validate_provider_metadata(ProviderMetadata(name="Demo"))

    assert report.ok is True
    assert _codes(report) == {"provider.no_description"}


# --- Provider configuration -----------------------------------------------------


def test_stdio_without_a_command_is_an_error_only_once_metadata_is_known() -> None:
    """Alone, the config is fine -- it is only wrong *for this provider*,
    which is why the metadata argument exists."""
    config = ProviderConfig(transport="stdio")
    metadata = ProviderMetadata(name="Demo", description="d", transport="stdio")

    assert validate_provider_config(config).ok is True
    assert "config.missing_transport_option" in _codes(validate_provider_config(config, metadata))


def test_supplying_the_required_option_clears_the_error() -> None:
    config = ProviderConfig(transport="stdio", options={"command": "demo-server"})
    metadata = ProviderMetadata(name="Demo", description="d", transport="stdio")

    assert validate_provider_config(config, metadata).ok is True


def test_config_transport_falls_back_to_metadata_transport() -> None:
    """An empty ``config.transport`` means "use what the provider
    declared"; the validator must resolve it the same way the runtime
    does or it would report a phantom problem."""
    config = ProviderConfig(transport="", options={"url": "ws://localhost:1"})
    metadata = ProviderMetadata(name="Demo", description="d", transport="websocket")

    assert validate_provider_config(config, metadata).ok is True


@pytest.mark.parametrize(
    ("field", "value"),
    [("reconnect", 0), ("retry", 0)],
)
def test_non_positive_attempt_counts_are_errors(field: str, value: int) -> None:
    from jarvis.core.mcp.providers.metadata import ReconnectPolicy, RetryPolicy

    kwargs: dict[str, object] = {}
    if field == "reconnect":
        kwargs["reconnect"] = ReconnectPolicy(max_attempts=value)
    else:
        kwargs["retry"] = RetryPolicy(max_attempts=value)

    report = validate_provider_config(ProviderConfig(transport="stdio", **kwargs))  # type: ignore[arg-type]

    assert report.ok is False


# --- Standalone transport config ------------------------------------------------


def test_unknown_transport_short_circuits() -> None:
    """Reporting missing options for a transport that does not exist
    would be noise on top of the real problem."""
    report = validate_transport_config("carrier_pigeon", {"command": "x"})

    assert _codes(report) == {"transport.unknown"}


def test_unused_option_key_is_a_warning() -> None:
    """A stray key works -- the transport ignores it -- but it is almost
    always a typo, so it is reported without blocking."""
    report = validate_transport_config("stdio", {"command": "x", "prot": 8080})

    assert report.ok is True
    assert "transport.unknown_option" in _codes(report)


def test_request_timeout_is_accepted_by_every_transport() -> None:
    """Shared across all of them, so it must not trip the unknown-key
    warning for any single one."""
    for transport in ("stdio", "websocket", "http", "ipc"):
        options = {"request_timeout_seconds": 5.0}
        options[{"stdio": "command", "ipc": "endpoint"}.get(transport, "url")] = "x"
        assert "transport.unknown_option" not in _codes(
            validate_transport_config(transport, options)
        )


# --- Authentication -------------------------------------------------------------


def test_token_methods_require_a_token() -> None:
    assert "auth.missing_token" in _codes(validate_auth(AuthMethod.BEARER_TOKEN, {}))
    assert validate_auth(AuthMethod.BEARER_TOKEN, {"token": "t"}).ok is True


def test_none_method_needs_no_token() -> None:
    assert validate_auth(AuthMethod.NONE, {}).issues == ()


def test_unsupported_method_is_reported_only_when_a_registry_is_supplied() -> None:
    """Without a registry the validator cannot know what this build
    supports, and guessing would produce a false error."""
    strategies = build_default_strategy_registry()

    assert validate_auth(AuthMethod.OAUTH2, {}).issues == ()
    assert "auth.unsupported_method" in _codes(
        validate_auth(AuthMethod.OAUTH2, {}, strategies=strategies)
    )


# --- Registry consistency -------------------------------------------------------


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "perm.json")


@pytest.fixture
def auth_manager(tmp_path: Path, permissions: PermissionModel) -> MCPAuthManager:
    return MCPAuthManager(
        CredentialStore(tmp_path / "creds.json"),
        build_default_strategy_registry(),
        permissions,
    )


def test_provider_needing_an_unregistered_transport_is_an_error() -> None:
    """Both objects are valid on their own. Only together do they show
    that this provider can never connect in this build."""
    registry = MCPProviderRegistry()
    registry.register(
        "demo",
        ProviderMetadata(name="Demo", description="d", transport="websocket"),
        ProviderConfig(transport="websocket", options={"url": "ws://localhost:1"}),
    )

    report = validate_registry_consistency(
        provider_registry=registry, transport_registry=TransportFactoryRegistry()
    )

    assert report.ok is False
    assert "registry.transport_not_registered" in _codes(report)


def test_registered_transport_clears_the_error() -> None:
    registry = MCPProviderRegistry()
    registry.register(
        "demo",
        ProviderMetadata(name="Demo", description="d", transport="websocket"),
        ProviderConfig(transport="websocket", options={"url": "ws://localhost:1"}),
    )
    transports = TransportFactoryRegistry()
    transports.register("websocket", lambda config: object())  # type: ignore[arg-type,return-value]

    report = validate_registry_consistency(
        provider_registry=registry, transport_registry=transports
    )

    assert "registry.transport_not_registered" not in _codes(report)


def test_pending_permissions_warn_rather_than_block(auth_manager: MCPAuthManager) -> None:
    """An undecided grant is the normal state right after install -- the
    provider connects, and capabilities needing the scope are negotiated
    away. That is a caveat, not a failure."""
    registry = MCPProviderRegistry()
    registry.register(
        "demo",
        ProviderMetadata(
            name="Demo",
            description="d",
            transport="in_process",
            required_permissions=("agent_tools",),
        ),
        ProviderConfig(transport="in_process"),
    )
    transports = TransportFactoryRegistry()
    transports.register("in_process", lambda config: object())  # type: ignore[arg-type,return-value]

    report = validate_registry_consistency(
        provider_registry=registry,
        transport_registry=transports,
        auth_manager=auth_manager,
    )

    assert report.ok is True
    assert "registry.permissions_pending" in _codes(report)


@pytest.mark.asyncio
async def test_granted_permissions_drop_the_warning(
    auth_manager: MCPAuthManager, permissions: PermissionModel
) -> None:
    registry = MCPProviderRegistry()
    registry.register(
        "demo",
        ProviderMetadata(
            name="Demo",
            description="d",
            transport="in_process",
            required_permissions=("agent_tools",),
        ),
        ProviderConfig(transport="in_process"),
    )
    transports = TransportFactoryRegistry()
    transports.register("in_process", lambda config: object())  # type: ignore[arg-type,return-value]
    await permissions.grant("mcp:demo", "agent_tools")

    report = validate_registry_consistency(
        provider_registry=registry,
        transport_registry=transports,
        auth_manager=auth_manager,
    )

    assert "registry.permissions_pending" not in _codes(report)


def test_disabled_provider_is_a_warning() -> None:
    registry = MCPProviderRegistry()
    registry.register(
        "demo",
        ProviderMetadata(name="Demo", description="d", transport="in_process"),
        ProviderConfig(transport="in_process", enabled=False),
    )
    transports = TransportFactoryRegistry()
    transports.register("in_process", lambda config: object())  # type: ignore[arg-type,return-value]

    report = validate_registry_consistency(
        provider_registry=registry, transport_registry=transports
    )

    assert report.ok is True
    assert "registry.provider_disabled" in _codes(report)


def test_unimplemented_auth_methods_are_reported_honestly() -> None:
    """M10.5 ships no OAuth2 flow. Rather than pretend otherwise, the
    validator states which vocabulary entries have no implementation --
    the same honesty ``/api/v1/mcp/auth/methods`` reports."""
    report = validate_registry_consistency(
        provider_registry=MCPProviderRegistry(),
        transport_registry=TransportFactoryRegistry(),
        strategies=build_default_strategy_registry(),
    )

    subjects = {i.subject for i in report.warnings if i.code == "registry.auth_method_unsupported"}
    assert subjects == {"oauth2", "client_credentials"}
    assert report.ok is True


def test_empty_platform_validates_clean() -> None:
    """No providers, no strategies supplied: nothing to be inconsistent
    about, so silence is the right answer."""
    report = validate_registry_consistency(
        provider_registry=MCPProviderRegistry(),
        transport_registry=TransportFactoryRegistry(),
    )

    assert report.issues == ()
