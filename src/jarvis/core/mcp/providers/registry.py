"""Provider Registry -- Milestone 10.5 Task Group C, deliverables 2 and 6.

Owns registration, lookup, enumeration, metadata and discovery for MCP
providers, in the same shape
:class:`~jarvis.core.mcp.capabilities.MCPCapabilityRegistry` (Task Group
A) and :class:`~jarvis.services.search_service.SearchService`'s provider
registry (M10A) already established: register / unregister / get / list,
keyed by a stable id, with no hardcoded provider list and no
``isinstance`` dispatch anywhere inside.

**Registration is inert.** A registered provider has been *declared*,
not started -- no transport is created, no subprocess spawned, no socket
opened. That is what lets :meth:`discover` answer "what is available
and what would it need" without side effects, and it is why lifecycle
lives in ``manager.py`` rather than here. This registry knows what
providers *are*; the manager knows what they are *doing*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.providers.metadata import (
    MCPProviderError,
    ProviderConfig,
    ProviderMetadata,
    ProviderState,
)

if TYPE_CHECKING:
    from collections.abc import Collection

_logger = get_logger("jarvis.core.mcp.providers.registry")


class ProviderRecord:
    """One registered provider: its declaration, its settings, and its
    current resting state.

    Mutable state on an otherwise-declarative record, matching
    ``PluginRegistry._Entry``'s shape for the same reason -- transitions
    are recorded in place rather than by rebuilding a frozen record on
    every move.
    """

    __slots__ = ("config", "error", "metadata", "provider", "provider_id", "state")

    def __init__(
        self,
        provider_id: str,
        metadata: ProviderMetadata,
        config: ProviderConfig,
        provider: Any = None,
    ) -> None:
        self.provider_id = provider_id
        self.metadata = metadata
        self.config = config
        self.provider = provider
        self.state: ProviderState = ProviderState.REGISTERED
        self.error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "error": self.error,
            "enabled": self.config.enabled,
            "transport": self.config.resolved_transport(self.metadata),
            "metadata": self.metadata.as_dict(),
            "config": self.config.as_dict(),
        }


class MCPProviderRegistry:
    """The one place a provider is declared and looked up."""

    def __init__(self) -> None:
        self._records: dict[str, ProviderRecord] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(
        self,
        provider_id: str,
        metadata: ProviderMetadata,
        config: ProviderConfig | None = None,
        provider: Any = None,
        *,
        replace: bool = False,
    ) -> ProviderRecord:
        """Validates and records a provider.

        A duplicate id is an error unless *replace* is passed --
        the same deliberate divergence from "last registration wins"
        ``MCPCapabilityRegistry`` makes, and for the same reason: a
        provider silently shadowing another's id would change what an
        existing permission grant and an existing connection refer to.
        """
        if not provider_id.strip():
            raise MCPProviderError("Provider id must not be empty.")
        if provider_id in self._records and not replace:
            raise MCPProviderError(
                f"Provider {provider_id!r} is already registered; "
                "pass replace=True to override it deliberately."
            )

        resolved_config = config or ProviderConfig()
        metadata.validate()
        resolved_config.validate()

        record = ProviderRecord(provider_id, metadata, resolved_config, provider)
        self._records[provider_id] = record
        _logger.info("MCP provider registered: {} ({})", provider_id, metadata.transport)
        return record

    def unregister(self, provider_id: str) -> bool:
        """Returns whether *provider_id* was actually registered, so a
        caller can distinguish "removed" from "was never there"."""
        removed = self._records.pop(provider_id, None)
        if removed is None:
            return False
        _logger.info("MCP provider unregistered: {}", provider_id)
        return True

    def clear(self) -> None:
        self._records.clear()

    # ------------------------------------------------------------------
    # Lookup / enumeration
    # ------------------------------------------------------------------
    def get(self, provider_id: str) -> ProviderRecord | None:
        return self._records.get(provider_id)

    def require(self, provider_id: str) -> ProviderRecord:
        """:meth:`get` for callers that cannot proceed without it --
        raises with a message naming the id rather than returning
        ``None`` for them to dereference."""
        record = self._records.get(provider_id)
        if record is None:
            raise MCPProviderError(f"Provider {provider_id!r} is not registered.")
        return record

    def has(self, provider_id: str) -> bool:
        return provider_id in self._records

    def metadata(self, provider_id: str) -> ProviderMetadata | None:
        record = self._records.get(provider_id)
        return None if record is None else record.metadata

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._records)

    def __len__(self) -> int:
        return len(self._records)

    def enumerate(self) -> tuple[ProviderRecord, ...]:
        return tuple(self._records.values())

    # ------------------------------------------------------------------
    # Discovery (deliverable 6)
    # ------------------------------------------------------------------
    def discover(
        self,
        *,
        transport: str | None = None,
        capability: str | None = None,
        state: ProviderState | str | None = None,
        protocol: str | None = None,
        permission: str | None = None,
        enabled_only: bool = False,
    ) -> tuple[ProviderRecord, ...]:
        """Filter registered providers.

        Every filter is a plain attribute match, deliberately -- discovery
        answers "which providers match these constraints", not "search".
        Universal Search (M10A) remains the surface for the latter, and
        duplicating a ranking engine here would be exactly the parallel
        system this task group forbids.

        Filters combine with AND. Omitted filters do not constrain.
        """
        results = tuple(self._records.values())

        if transport is not None:
            results = tuple(
                r for r in results if r.config.resolved_transport(r.metadata) == transport
            )
        if capability is not None:
            results = tuple(r for r in results if capability in r.metadata.capabilities)
        if state is not None:
            wanted = state.value if isinstance(state, ProviderState) else state
            results = tuple(r for r in results if r.state.value == wanted)
        if protocol is not None:
            results = tuple(r for r in results if protocol in r.metadata.supported_protocols)
        if permission is not None:
            results = tuple(r for r in results if permission in r.metadata.required_permissions)
        if enabled_only:
            results = tuple(r for r in results if r.config.enabled)

        return results

    def required_scopes(self, provider_ids: Collection[str] | None = None) -> set[str]:
        """Every permission scope the named providers request (all of
        them when *provider_ids* is omitted) -- the input a caller
        resolves against ``PermissionModel`` before connecting."""
        records = (
            self._records.values()
            if provider_ids is None
            else [r for pid, r in self._records.items() if pid in provider_ids]
        )
        return {scope for record in records for scope in record.metadata.required_permissions}

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(record.as_dict() for record in self._records.values())
