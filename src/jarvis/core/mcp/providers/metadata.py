"""Provider metadata, configuration and state -- Milestone 10.5 Task
Group C, deliverables 4 and 5.

Plain frozen dataclasses, no I/O, no behaviour: a provider's *identity*
and its *settings* are data the registry validates and the manager
acts on. Keeping them inert is what lets the registry answer discovery
queries (deliverable 6) without constructing a transport, starting a
subprocess, or touching the network -- describing a provider must never
have side effects.

Deliberately mirrors the shape M9's plugin manifest already
established: a declarative record naming what a thing is, what it
needs, and what permissions it *requests* (never what it has been
granted -- that decision stays in ``PermissionModel``).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from jarvis.core.interfaces.mcp import (
    TRANSPORT_TYPES,
    MCPError,
)
from jarvis.core.mcp.negotiation import SUPPORTED_PROTOCOL_VERSIONS
from jarvis.core.plugins.sdk import PERMISSION_SCOPES


class MCPProviderError(MCPError):
    """An invalid provider declaration, or an illegal lifecycle move."""


class ProviderState(enum.StrEnum):
    """A provider's resting state.

    ``RESUMED`` is deliberately absent: resuming lands a provider back
    in ``CONNECTED``, and inventing a state that nothing rests in would
    make the state machine lie. The *transition* is still observable --
    see ``MCPProviderStateChangedEvent.action``.
    """

    REGISTERED = "registered"
    INITIALIZED = "initialized"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    SUSPENDED = "suspended"
    FAILED = "failed"
    REMOVED = "removed"


#: Lifecycle transitions published on the relay. A superset of
#: :class:`ProviderState` -- it includes ``resumed``, which is a move
#: rather than a resting place.
PROVIDER_ACTIONS: frozenset[str] = frozenset(
    {
        "registered",
        "initialized",
        "connected",
        "disconnected",
        "suspended",
        "resumed",
        "failed",
        "removed",
    }
)


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """How hard to try when a connection drops. Defaults match
    ``MCPClientRuntime``'s own, so a provider that says nothing behaves
    exactly like a hand-registered connection."""

    enabled: bool = True
    max_attempts: int = 3
    backoff_seconds: float = 0.5


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """How a single failed *request* is retried, as distinct from a
    dropped *connection*. Separate because they fail for different
    reasons and a caller frequently wants one without the other."""

    enabled: bool = False
    max_attempts: int = 2
    backoff_seconds: float = 0.25


@dataclass(frozen=True, slots=True)
class HeartbeatSettings:
    """Per-provider override of the global heartbeat cadence (Task
    Group B). ``interval_seconds <= 0`` means "use the global setting"
    rather than "never" -- an explicit ``enabled=False`` is how a
    provider opts out, so the two intents cannot be confused."""

    enabled: bool = True
    interval_seconds: float = 0.0


@dataclass(frozen=True, slots=True)
class ProviderMetadata:
    """What a provider *is*. Declarative, and never mutated after
    registration."""

    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    #: Capability names this provider expects to offer. Advisory only --
    #: the authoritative list is whatever negotiation actually accepted
    #: at connect time, which is why this is metadata and not state.
    capabilities: tuple[str, ...] = ()
    transport: str = "stdio"
    #: Scopes this provider *requests*, drawn from the existing
    #: ``PERMISSION_SCOPES``. Requesting is never granting.
    required_permissions: tuple[str, ...] = ()
    supported_protocols: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    tags: tuple[str, ...] = ()

    def validate(self) -> None:
        """Raises :class:`MCPProviderError` on anything the registry
        must not accept. Called at registration, so a malformed
        provider fails loudly at declaration rather than at first
        connect."""
        if not self.name.strip():
            raise MCPProviderError("Provider name must not be empty.")
        if self.transport not in TRANSPORT_TYPES:
            raise MCPProviderError(
                f"Provider {self.name!r} declares unknown transport {self.transport!r}; "
                f"allowed: {sorted(TRANSPORT_TYPES)}"
            )
        unknown_scopes = sorted(set(self.required_permissions) - PERMISSION_SCOPES)
        if unknown_scopes:
            raise MCPProviderError(
                f"Provider {self.name!r} declares unknown permission scope(s) "
                f"{unknown_scopes}; allowed: {sorted(PERMISSION_SCOPES)}"
            )
        if not self.supported_protocols:
            raise MCPProviderError(
                f"Provider {self.name!r} declares no supported protocol versions."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "transport": self.transport,
            "required_permissions": list(self.required_permissions),
            "supported_protocols": list(self.supported_protocols),
            "tags": list(self.tags),
        }


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    """How a provider should *run*.

    ``transport`` here overrides the metadata's declared default, so a
    deployment can move a provider from stdio to websocket without
    editing the provider itself -- the separation that keeps
    "what it is" and "how this install runs it" from drifting into one
    another.

    ``options`` is the transport's own config dict, passed straight to
    ``TransportFactoryRegistry.create``. Task Group C introduces no
    provider-specific keys: this is the generic escape hatch every
    transport already reads from.
    """

    enabled: bool = True
    transport: str = ""
    options: dict[str, Any] = field(default_factory=dict)
    reconnect: ReconnectPolicy = field(default_factory=ReconnectPolicy)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    heartbeat: HeartbeatSettings = field(default_factory=HeartbeatSettings)

    def resolved_transport(self, metadata: ProviderMetadata) -> str:
        """Config wins over metadata; metadata is the fallback."""
        return self.transport or metadata.transport

    def validate(self) -> None:
        if self.transport and self.transport not in TRANSPORT_TYPES:
            raise MCPProviderError(
                f"Configuration declares unknown transport {self.transport!r}; "
                f"allowed: {sorted(TRANSPORT_TYPES)}"
            )
        if self.reconnect.max_attempts < 1:
            raise MCPProviderError("reconnect.max_attempts must be at least 1.")
        if self.retry.max_attempts < 1:
            raise MCPProviderError("retry.max_attempts must be at least 1.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "transport": self.transport,
            # Option values can carry credentials once M11's providers
            # exist; only the key names are reported, never the values.
            "option_keys": sorted(self.options),
            "reconnect": {
                "enabled": self.reconnect.enabled,
                "max_attempts": self.reconnect.max_attempts,
                "backoff_seconds": self.reconnect.backoff_seconds,
            },
            "retry": {
                "enabled": self.retry.enabled,
                "max_attempts": self.retry.max_attempts,
                "backoff_seconds": self.retry.backoff_seconds,
            },
            "heartbeat": {
                "enabled": self.heartbeat.enabled,
                "interval_seconds": self.heartbeat.interval_seconds,
            },
        }
