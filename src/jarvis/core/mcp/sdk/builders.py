"""MCP SDK builders -- Milestone 10.5 Task Group E, deliverable 1.

The surface a future provider author works against. Each builder is a
small fluent wrapper that produces the **existing** runtime model --
``MCPCapability``, ``ProviderMetadata``, ``ProviderConfig``, a transport
config dict, a credential request. No new runtime type is introduced
here, and nothing in the runtime knows these builders exist.

**Why builders at all, given the models are already plain dataclasses.**
Three reasons that are real rather than ceremonial:

1. *Validation at the point of construction.* ``build()`` validates and
   raises with the whole list of problems, so an author learns about a
   bad permission scope while writing the provider rather than at
   connect time.
2. *Discoverability.* ``.with_permission("agent_tools")`` is
   autocomplete-friendly and rejects an unknown scope immediately;
   ``required_permissions=("agent_tolls",)`` is a typo that survives
   until runtime.
3. *Insulation from internal shape.* An author touches
   ``CapabilityBuilder``, not the constructor of a dataclass the runtime
   is free to extend. Adding a field to ``MCPCapability`` does not break
   anyone using the builder.

The dataclasses stay public and directly constructible -- the builders
are a convenience, not a gate. Anyone who prefers the raw model keeps
using it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from jarvis.core.interfaces.mcp import MCPCapability
from jarvis.core.mcp.auth.credentials import AuthMethod, MCPAuthError
from jarvis.core.mcp.providers.metadata import (
    HeartbeatSettings,
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ReconnectPolicy,
    RetryPolicy,
)
from jarvis.core.mcp.sdk.validation import (
    ValidationReport,
    validate_auth,
    validate_capability,
    validate_provider_config,
    validate_provider_metadata,
    validate_transport_config,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from jarvis.core.mcp.capabilities import MCPCapabilityRegistry
    from jarvis.core.mcp.providers.manager import MCPProviderManager
    from jarvis.core.mcp.providers.registry import ProviderRecord


class SDKValidationError(MCPProviderError):
    """Raised by ``build()`` when the assembled object is invalid.

    Carries the whole :class:`ValidationReport` rather than only the
    first message, because an author fixing a provider wants every
    problem at once.
    """

    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        detail = "; ".join(f"[{i.code}] {i.message}" for i in report.errors)
        super().__init__(f"Validation failed: {detail}")


class CapabilityBuilder:
    """Assembles an :class:`MCPCapability`."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._version = "1.0.0"
        self._kind = "tool"
        self._description = ""
        self._permissions: list[str] = []
        self._metadata: dict[str, Any] = {}

    def version(self, version: str) -> Self:
        self._version = version
        return self

    def kind(self, kind: str) -> Self:
        self._kind = kind
        return self

    def describe(self, description: str) -> Self:
        self._description = description
        return self

    def with_permission(self, *scopes: str) -> Self:
        """Adds required scopes. Duplicates are collapsed, so declaring
        the same scope twice is harmless rather than a subtle bug."""
        for scope in scopes:
            if scope not in self._permissions:
                self._permissions.append(scope)
        return self

    def with_metadata(self, **entries: Any) -> Self:
        self._metadata.update(entries)
        return self

    def draft(self) -> MCPCapability:
        """The assembled capability **without** validating -- for a
        caller that wants to inspect or validate it separately."""
        return MCPCapability(
            name=self._name,
            version=self._version,
            kind=self._kind,
            description=self._description,
            permissions=tuple(self._permissions),
            metadata=dict(self._metadata),
        )

    def validate(self) -> ValidationReport:
        return validate_capability(self.draft())

    def build(self) -> MCPCapability:
        capability = self.draft()
        report = validate_capability(capability)
        if not report.ok:
            raise SDKValidationError(report)
        return capability


class ProviderBuilder:
    """Assembles a :class:`ProviderMetadata`."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._version = "1.0.0"
        self._author = ""
        self._description = ""
        self._capabilities: list[str] = []
        self._transport = "stdio"
        self._permissions: list[str] = []
        self._protocols: tuple[str, ...] | None = None
        self._tags: list[str] = []

    def version(self, version: str) -> Self:
        self._version = version
        return self

    def author(self, author: str) -> Self:
        self._author = author
        return self

    def describe(self, description: str) -> Self:
        self._description = description
        return self

    def transport(self, transport: str) -> Self:
        self._transport = transport
        return self

    def with_capability(self, *names: str | MCPCapability) -> Self:
        """Accepts a name or a built capability, so an author can pass
        the object they already have rather than re-typing its name."""
        for entry in names:
            name = entry.name if isinstance(entry, MCPCapability) else entry
            if name not in self._capabilities:
                self._capabilities.append(name)
        return self

    def with_permission(self, *scopes: str) -> Self:
        for scope in scopes:
            if scope not in self._permissions:
                self._permissions.append(scope)
        return self

    def with_protocols(self, *versions: str) -> Self:
        self._protocols = tuple(versions)
        return self

    def with_tag(self, *tags: str) -> Self:
        for tag in tags:
            if tag not in self._tags:
                self._tags.append(tag)
        return self

    def draft(self) -> ProviderMetadata:
        kwargs: dict[str, Any] = {
            "name": self._name,
            "version": self._version,
            "author": self._author,
            "description": self._description,
            "capabilities": tuple(self._capabilities),
            "transport": self._transport,
            "required_permissions": tuple(self._permissions),
            "tags": tuple(self._tags),
        }
        if self._protocols is not None:
            kwargs["supported_protocols"] = self._protocols
        return ProviderMetadata(**kwargs)

    def validate(self) -> ValidationReport:
        return validate_provider_metadata(self.draft())

    def build(self) -> ProviderMetadata:
        metadata = self.draft()
        report = validate_provider_metadata(metadata)
        if not report.ok:
            raise SDKValidationError(report)
        return metadata


class TransportBuilder:
    """Assembles the transport half of a :class:`ProviderConfig`.

    Deliberately produces a config dict rather than a live transport:
    building one would spawn a subprocess or open a socket, and an SDK
    call named ``build()`` must never do that.
    """

    def __init__(self, transport: str) -> None:
        self._transport = transport
        self._options: dict[str, Any] = {}

    def option(self, key: str, value: Any) -> Self:
        self._options[key] = value
        return self

    def options(self, **entries: Any) -> Self:
        self._options.update(entries)
        return self

    def command(self, command: str, *args: str) -> Self:
        """stdio convenience."""
        self._options["command"] = command
        if args:
            self._options["args"] = list(args)
        return self

    def url(self, url: str) -> Self:
        """websocket/http convenience."""
        self._options["url"] = url
        return self

    def endpoint(self, endpoint: str) -> Self:
        """ipc convenience."""
        self._options["endpoint"] = endpoint
        return self

    def timeout(self, seconds: float) -> Self:
        self._options["request_timeout_seconds"] = seconds
        return self

    @property
    def transport_type(self) -> str:
        return self._transport

    def draft(self) -> dict[str, Any]:
        return dict(self._options)

    def validate(self) -> ValidationReport:
        return validate_transport_config(self._transport, self._options)

    def build(self) -> dict[str, Any]:
        report = self.validate()
        if not report.ok:
            raise SDKValidationError(report)
        return dict(self._options)


class AuthBuilder:
    """Assembles an authentication request for ``MCPAuthManager``.

    Holds a secret in memory only as long as the caller holds the
    builder, and redacts it in ``repr`` for the same reason
    ``Credential`` does.
    """

    def __init__(self, method: AuthMethod | str) -> None:
        # Coerced rather than merely annotated: an author writing
        # ``AuthBuilder("bearer_tokn")`` should fail here, on the typo,
        # not three calls later where the value is finally compared.
        self._method = AuthMethod(method)
        self._request: dict[str, Any] = {}

    def __repr__(self) -> str:
        return f"AuthBuilder(method={self._method.value!r}, keys={sorted(self._request)!r})"

    __str__ = __repr__

    def token(self, token: str) -> Self:
        self._request["token"] = token
        return self

    def account(self, account_id: str) -> Self:
        self._request["account_id"] = account_id
        return self

    def with_scope(self, *scopes: str) -> Self:
        existing = list(self._request.get("scopes") or [])
        for scope in scopes:
            if scope not in existing:
                existing.append(scope)
        self._request["scopes"] = existing
        return self

    @property
    def method(self) -> AuthMethod:
        return self._method

    def draft(self) -> dict[str, Any]:
        return dict(self._request)

    def validate(self, *, strategies: Any = None) -> ValidationReport:
        return validate_auth(self._method, self._request, strategies=strategies)

    def build(self) -> tuple[AuthMethod, dict[str, Any]]:
        report = validate_auth(self._method, self._request)
        if not report.ok:
            raise MCPAuthError("; ".join(f"[{i.code}] {i.message}" for i in report.errors))
        return self._method, dict(self._request)


class ConfigBuilder:
    """Assembles a :class:`ProviderConfig`."""

    def __init__(self, transport: str = "") -> None:
        self._enabled = True
        self._transport = transport
        self._options: dict[str, Any] = {}
        self._reconnect = ReconnectPolicy()
        self._retry = RetryPolicy()
        self._heartbeat = HeartbeatSettings()

    def enabled(self, enabled: bool = True) -> Self:
        self._enabled = enabled
        return self

    def transport(self, transport: str, options: dict[str, Any] | None = None) -> Self:
        self._transport = transport
        if options:
            self._options.update(options)
        return self

    def from_transport(self, builder: TransportBuilder) -> Self:
        """Adopts a :class:`TransportBuilder`'s type and options in one
        step, so the two builders compose rather than duplicating."""
        self._transport = builder.transport_type
        self._options.update(builder.draft())
        return self

    def options(self, **entries: Any) -> Self:
        self._options.update(entries)
        return self

    def reconnect(
        self, *, enabled: bool = True, max_attempts: int = 3, backoff_seconds: float = 0.5
    ) -> Self:
        self._reconnect = ReconnectPolicy(
            enabled=enabled, max_attempts=max_attempts, backoff_seconds=backoff_seconds
        )
        return self

    def retry(
        self, *, enabled: bool = False, max_attempts: int = 2, backoff_seconds: float = 0.25
    ) -> Self:
        self._retry = RetryPolicy(
            enabled=enabled, max_attempts=max_attempts, backoff_seconds=backoff_seconds
        )
        return self

    def heartbeat(self, *, enabled: bool = True, interval_seconds: float = 0.0) -> Self:
        self._heartbeat = HeartbeatSettings(enabled=enabled, interval_seconds=interval_seconds)
        return self

    def draft(self) -> ProviderConfig:
        return ProviderConfig(
            enabled=self._enabled,
            transport=self._transport,
            options=dict(self._options),
            reconnect=self._reconnect,
            retry=self._retry,
            heartbeat=self._heartbeat,
        )

    def validate(self, metadata: ProviderMetadata | None = None) -> ValidationReport:
        return validate_provider_config(self.draft(), metadata)

    def build(self, metadata: ProviderMetadata | None = None) -> ProviderConfig:
        config = self.draft()
        report = validate_provider_config(config, metadata)
        if not report.ok:
            raise SDKValidationError(report)
        return config


# ---------------------------------------------------------------------------
# Registry helpers (deliverable 1) -- thin, validating wrappers
# ---------------------------------------------------------------------------
async def register_provider(
    manager: MCPProviderManager,
    provider_id: str,
    metadata: ProviderMetadata,
    config: ProviderConfig | None = None,
    *,
    replace: bool = False,
) -> ProviderRecord:
    """Validates metadata *and* config together, then installs.

    ``MCPProviderManager.install`` already validates each object on its
    own; what this adds is the cross-object check -- that the resolved
    transport actually has the options it needs -- before anything is
    registered, so a broken provider never enters the registry at all.
    """
    resolved = config or ProviderConfig()
    report = validate_provider_metadata(metadata).merge(
        validate_provider_config(resolved, metadata)
    )
    if not report.ok:
        raise SDKValidationError(report)
    return await manager.install(provider_id, metadata, resolved, replace=replace)


async def expose_capabilities(
    server: Any,
    capabilities: Iterable[MCPCapability],
    *,
    replace: bool = False,
) -> tuple[str, ...]:
    """Validates every capability, then exposes them on the server
    runtime. All-or-nothing: a batch with one invalid entry registers
    none of them, so a partial exposure never leaves the server in a
    state the author did not intend."""
    capabilities = list(capabilities)
    report = ValidationReport()
    for capability in capabilities:
        report = report.merge(validate_capability(capability))
    if not report.ok:
        raise SDKValidationError(report)

    for capability in capabilities:
        await server.expose(capability, replace=replace)
    return tuple(c.name for c in capabilities)


def capability_names(registry: MCPCapabilityRegistry) -> tuple[str, ...]:
    """Convenience read that keeps an SDK consumer off the registry's
    internals."""
    return registry.names
