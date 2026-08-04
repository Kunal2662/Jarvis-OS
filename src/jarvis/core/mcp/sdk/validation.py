"""MCP validation framework -- Milestone 10.5 Task Group E, deliverable 3.

Reusable validators for capabilities, providers, authentication,
configuration, transports, metadata, and **registry consistency**.

**What this adds over the validation already in the runtime.** Each
model already validates *itself* at construction (``ProviderMetadata.
validate()``, ``MCPCapabilityRegistry._validate``, ...) and that stays
where it is -- a model that can be constructed invalid would be a worse
design. What no single model can check is whether a *set* of
independently-valid objects is coherent: a provider declaring a
transport nothing registered, an auth method no strategy implements, a
capability requiring a permission that will never be granted. Those are
cross-object questions, so they live here.

**Reports, never raises.** A validator returns every problem it finds
rather than stopping at the first, because a developer fixing a provider
wants the whole list. Severity separates "this will not work"
(``ERROR``) from "this will work but probably is not what you meant"
(``WARNING``) -- collapsing them would make the warning either
ignorable noise or a false blocker.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.mcp import (
    CAPABILITY_KINDS,
    TRANSPORT_TYPES,
    MCPCapability,
)
from jarvis.core.mcp.auth.credentials import AuthMethod
from jarvis.core.mcp.negotiation import SUPPORTED_PROTOCOL_VERSIONS
from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata
from jarvis.core.mcp.transport import TRANSPORT_TRAITS
from jarvis.core.plugins.sdk import PERMISSION_SCOPES

if TYPE_CHECKING:
    from collections.abc import Iterable

    from jarvis.core.mcp.auth.manager import MCPAuthManager
    from jarvis.core.mcp.auth.strategies import AuthStrategyRegistry
    from jarvis.core.mcp.providers.registry import MCPProviderRegistry
    from jarvis.core.mcp.transport import TransportFactoryRegistry


class Severity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One problem, with a stable ``code`` a caller can branch on rather
    than string-matching the message."""

    code: str
    message: str
    severity: Severity = Severity.ERROR
    subject: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity.value,
            "subject": self.subject,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Every issue found. ``ok`` ignores warnings deliberately: a
    warning describes something that will work."""

    issues: tuple[ValidationIssue, ...] = field(default_factory=tuple)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: ValidationReport) -> ValidationReport:
        return ValidationReport(issues=self.issues + other.issues)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.as_dict() for i in self.issues],
        }


def _report(issues: list[ValidationIssue]) -> ValidationReport:
    return ValidationReport(issues=tuple(issues))


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------
def validate_capability(capability: MCPCapability) -> ValidationReport:
    issues: list[ValidationIssue] = []
    subject = capability.name or "<unnamed>"

    if not capability.name.strip():
        issues.append(
            ValidationIssue(
                "capability.name_empty", "Capability name must not be empty.", subject=subject
            )
        )
    if capability.kind not in CAPABILITY_KINDS:
        issues.append(
            ValidationIssue(
                "capability.unknown_kind",
                f"Unknown capability kind {capability.kind!r}; "
                f"allowed: {sorted(CAPABILITY_KINDS)}.",
                subject=subject,
            )
        )
    unknown = sorted(set(capability.permissions) - PERMISSION_SCOPES)
    if unknown:
        issues.append(
            ValidationIssue(
                "capability.unknown_permission",
                f"Unknown permission scope(s) {unknown}; allowed: {sorted(PERMISSION_SCOPES)}.",
                subject=subject,
            )
        )
    if not capability.description.strip():
        issues.append(
            ValidationIssue(
                "capability.no_description",
                "Capability has no description; an agent selecting tools has nothing to go on.",
                severity=Severity.WARNING,
                subject=subject,
            )
        )
    return _report(issues)


# ---------------------------------------------------------------------------
# Provider metadata / configuration
# ---------------------------------------------------------------------------
def validate_provider_metadata(metadata: ProviderMetadata) -> ValidationReport:
    issues: list[ValidationIssue] = []
    subject = metadata.name or "<unnamed>"

    if not metadata.name.strip():
        issues.append(
            ValidationIssue(
                "provider.name_empty", "Provider name must not be empty.", subject=subject
            )
        )
    if metadata.transport not in TRANSPORT_TYPES:
        issues.append(
            ValidationIssue(
                "provider.unknown_transport",
                f"Unknown transport {metadata.transport!r}; allowed: {sorted(TRANSPORT_TYPES)}.",
                subject=subject,
            )
        )
    unknown = sorted(set(metadata.required_permissions) - PERMISSION_SCOPES)
    if unknown:
        issues.append(
            ValidationIssue(
                "provider.unknown_permission",
                f"Unknown permission scope(s) {unknown}.",
                subject=subject,
            )
        )
    if not metadata.supported_protocols:
        issues.append(
            ValidationIssue(
                "provider.no_protocols",
                "Provider declares no supported protocol versions.",
                subject=subject,
            )
        )
    elif not set(metadata.supported_protocols) & set(SUPPORTED_PROTOCOL_VERSIONS):
        issues.append(
            ValidationIssue(
                "provider.no_common_protocol",
                f"None of {list(metadata.supported_protocols)} overlaps this build's "
                f"{list(SUPPORTED_PROTOCOL_VERSIONS)}; negotiation would always fail.",
                subject=subject,
            )
        )
    if not metadata.description.strip():
        issues.append(
            ValidationIssue(
                "provider.no_description",
                "Provider has no description.",
                severity=Severity.WARNING,
                subject=subject,
            )
        )
    return _report(issues)


def validate_provider_config(
    config: ProviderConfig, metadata: ProviderMetadata | None = None
) -> ValidationReport:
    """Validates settings, and -- when *metadata* is supplied -- that the
    resolved transport has the config keys it actually needs."""
    issues: list[ValidationIssue] = []

    if config.transport and config.transport not in TRANSPORT_TYPES:
        issues.append(
            ValidationIssue(
                "config.unknown_transport",
                f"Unknown transport {config.transport!r}; allowed: {sorted(TRANSPORT_TYPES)}.",
            )
        )
    if config.reconnect.max_attempts < 1:
        issues.append(
            ValidationIssue("config.bad_reconnect", "reconnect.max_attempts must be at least 1.")
        )
    if config.retry.max_attempts < 1:
        issues.append(ValidationIssue("config.bad_retry", "retry.max_attempts must be at least 1."))
    if config.heartbeat.interval_seconds < 0:
        issues.append(
            ValidationIssue(
                "config.bad_heartbeat", "heartbeat.interval_seconds must not be negative."
            )
        )

    if metadata is not None:
        issues.extend(_missing_transport_options(config, metadata))
    return _report(issues)


#: The config key each transport cannot function without. Derived from
#: the same declarative traits ``/api/v1/mcp/transports`` reports, so a
#: new transport is described in exactly one place.
_REQUIRED_OPTION: dict[str, str] = {
    "stdio": "command",
    "websocket": "url",
    "http": "url",
    "ipc": "endpoint",
}


def _missing_transport_options(
    config: ProviderConfig, metadata: ProviderMetadata
) -> list[ValidationIssue]:
    transport = config.resolved_transport(metadata)
    required = _REQUIRED_OPTION.get(transport)
    if required and not config.options.get(required):
        return [
            ValidationIssue(
                "config.missing_transport_option",
                f"Transport {transport!r} requires a {required!r} entry in options; "
                f"present keys: {sorted(config.options) or 'none'}.",
                subject=metadata.name,
            )
        ]
    return []


def validate_transport_config(transport: str, options: dict[str, Any]) -> ValidationReport:
    """Standalone transport-config check, for callers holding no
    provider (the CLI's ``validate`` on a bare config file, say)."""
    issues: list[ValidationIssue] = []
    if transport not in TRANSPORT_TYPES:
        issues.append(
            ValidationIssue(
                "transport.unknown",
                f"Unknown transport {transport!r}; allowed: {sorted(TRANSPORT_TYPES)}.",
                subject=transport,
            )
        )
        return _report(issues)

    required = _REQUIRED_OPTION.get(transport)
    if required and not options.get(required):
        issues.append(
            ValidationIssue(
                "transport.missing_option",
                f"Transport {transport!r} requires a {required!r} option.",
                subject=transport,
            )
        )
    known_keys = set(TRANSPORT_TRAITS.get(transport, {}).get("config_keys", []))
    unknown_keys = sorted(set(options) - known_keys - {"request_timeout_seconds"})
    if unknown_keys:
        issues.append(
            ValidationIssue(
                "transport.unknown_option",
                f"Option key(s) {unknown_keys} are not used by transport {transport!r}.",
                severity=Severity.WARNING,
                subject=transport,
            )
        )
    return _report(issues)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------
def validate_auth(
    method: AuthMethod,
    request: dict[str, Any] | None = None,
    *,
    strategies: AuthStrategyRegistry | None = None,
) -> ValidationReport:
    """Checks an authentication method and its request *before* anything
    is stored, so a developer learns about a missing token now rather
    than at first connect."""
    issues: list[ValidationIssue] = []
    payload = request or {}

    if strategies is not None and not strategies.supports(method):
        issues.append(
            ValidationIssue(
                "auth.unsupported_method",
                f"No strategy is registered for {method.value!r}; "
                f"supported: {list(strategies.supported_methods)}.",
                subject=method.value,
            )
        )

    needs_token = method in {
        AuthMethod.API_KEY,
        AuthMethod.BEARER_TOKEN,
        AuthMethod.PERSONAL_ACCESS_TOKEN,
    }
    if needs_token and not (payload.get("token") or payload.get("access_token")):
        issues.append(
            ValidationIssue(
                "auth.missing_token",
                f"{method.value} authentication requires a 'token' entry.",
                subject=method.value,
            )
        )
    return _report(issues)


# ---------------------------------------------------------------------------
# Registry consistency -- the cross-object checks nothing else can make
# ---------------------------------------------------------------------------
def validate_registry_consistency(
    *,
    provider_registry: MCPProviderRegistry,
    transport_registry: TransportFactoryRegistry,
    auth_manager: MCPAuthManager | None = None,
    strategies: AuthStrategyRegistry | None = None,
) -> ValidationReport:
    """Whether a set of independently-valid objects actually works
    together. This is the check no individual model can perform."""
    issues: list[ValidationIssue] = []

    for record in provider_registry.enumerate():
        pid = record.provider_id
        transport = record.config.resolved_transport(record.metadata)

        if not transport_registry.supports(transport):
            issues.append(
                ValidationIssue(
                    "registry.transport_not_registered",
                    f"Provider {pid!r} needs transport {transport!r}, which is not registered "
                    f"in this build (registered: "
                    f"{list(transport_registry.registered_types) or 'none'}).",
                    subject=pid,
                )
            )

        issues.extend(_missing_transport_options(record.config, record.metadata))

        if auth_manager is not None and record.metadata.required_permissions:
            granted = auth_manager.jarvis_scopes_granted(pid, record.metadata.required_permissions)
            pending = sorted(set(record.metadata.required_permissions) - granted)
            if pending:
                issues.append(
                    ValidationIssue(
                        "registry.permissions_pending",
                        f"Provider {pid!r} requests {pending}, still awaiting a grant decision; "
                        "capabilities needing them will be negotiated away.",
                        severity=Severity.WARNING,
                        subject=pid,
                    )
                )

        if not record.config.enabled:
            issues.append(
                ValidationIssue(
                    "registry.provider_disabled",
                    f"Provider {pid!r} is registered but disabled; it will not connect.",
                    severity=Severity.WARNING,
                    subject=pid,
                )
            )

    if strategies is not None:
        for method in (AuthMethod.OAUTH2, AuthMethod.CLIENT_CREDENTIALS):
            if not strategies.supports(method):
                issues.append(
                    ValidationIssue(
                        "registry.auth_method_unsupported",
                        f"{method.value!r} is in the vocabulary but no strategy implements it; "
                        "providers requiring it cannot authenticate.",
                        severity=Severity.WARNING,
                        subject=method.value,
                    )
                )
    return _report(issues)


def validate_capabilities(capabilities: Iterable[MCPCapability]) -> ValidationReport:
    """Every capability, plus the duplicate-name check a single
    capability cannot make about itself."""
    capabilities = list(capabilities)
    report = ValidationReport()
    for capability in capabilities:
        report = report.merge(validate_capability(capability))

    seen: set[str] = set()
    repeated: set[str] = set()
    for capability in capabilities:
        if capability.name in seen:
            repeated.add(capability.name)
        seen.add(capability.name)

    duplicates = sorted(repeated)
    if duplicates:
        report = report.merge(
            _report(
                [
                    ValidationIssue(
                        "capability.duplicate_name",
                        f"Duplicate capability name(s) {duplicates}; a later registration would "
                        "shadow an earlier one and change what a permission grant authorizes.",
                        subject=", ".join(duplicates),
                    )
                ]
            )
        )
    return report
