"""MCP Capability Registry -- Milestone 10.5 Task Group A, deliverable 1.

Owns registration, discovery and metadata for MCP capabilities, in
exactly the provider-registry shape
:class:`~jarvis.services.search_service.SearchService` already
established for ``ISearchSource`` (M10A): ``register``/``unregister``/
``get``/``list_capabilities``, keyed by the capability's own stable
``name``, with no hardcoded capability list and no ``isinstance``
dispatch anywhere inside this class. A future milestone adds a
capability by calling :meth:`register`; this file does not change.

One registry class serves both directions -- the capabilities JARVIS
*exposes* (``core/mcp/server.py``) and the capabilities a connected
peer *offers* (``core/mcp/client.py``) -- because a capability's shape
is identical either way. Each runtime owns its own instance rather than
sharing one global registry, so a misbehaving peer can never overwrite
a capability JARVIS itself exposes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.mcp import (
    CAPABILITY_KINDS,
    MCPCapability,
    MCPCapabilityError,
)
from jarvis.core.logging.logger import get_logger
from jarvis.core.plugins.sdk import PERMISSION_SCOPES

if TYPE_CHECKING:
    from collections.abc import Iterable

_logger = get_logger("jarvis.core.mcp.capabilities")


class MCPCapabilityRegistry:
    """A named collection of :class:`MCPCapability`, validated on entry."""

    def __init__(self, *, owner: str = "jarvis") -> None:
        #: Identifies whose capabilities these are -- ``"jarvis"`` for the
        #: server runtime's own, or an MCP server id for a peer's. Purely
        #: descriptive; used in log lines and status payloads.
        self.owner = owner
        self._capabilities: dict[str, MCPCapability] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------
    def register(self, capability: MCPCapability, *, replace: bool = False) -> None:
        """Validates and registers *capability*.

        Unlike ``SearchService.register_source``'s "last registration
        wins", a duplicate name is an error here unless *replace* is
        explicitly passed: a search source silently replacing itself on
        a plugin reload is benign, whereas one capability shadowing
        another's name would silently change what a permission grant
        actually authorizes.
        """
        self._validate(capability)
        if capability.name in self._capabilities and not replace:
            raise MCPCapabilityError(
                f"Capability {capability.name!r} is already registered on {self.owner!r}; "
                "pass replace=True to override it deliberately."
            )
        self._capabilities[capability.name] = capability
        _logger.info("MCP capability registered on {}: {}", self.owner, capability.name)

    def register_all(self, capabilities: Iterable[MCPCapability], *, replace: bool = False) -> None:
        for capability in capabilities:
            self.register(capability, replace=replace)

    def unregister(self, name: str) -> bool:
        """Returns whether *name* was actually registered -- so a caller
        can distinguish "removed" from "was never there" without a
        separate :meth:`has` call."""
        removed = self._capabilities.pop(name, None)
        if removed is None:
            return False
        _logger.info("MCP capability unregistered on {}: {}", self.owner, name)
        return True

    def clear(self) -> None:
        """Drops every capability. Used when a peer disconnects -- a
        stale capability list is worse than an empty one, since callers
        would otherwise negotiate against capabilities nothing is
        serving."""
        self._capabilities.clear()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def get(self, name: str) -> MCPCapability | None:
        return self._capabilities.get(name)

    def has(self, name: str) -> bool:
        return name in self._capabilities

    def list_capabilities(
        self,
        *,
        kind: str | None = None,
        required_permission: str | None = None,
    ) -> tuple[MCPCapability, ...]:
        """Every registered capability, optionally filtered.

        Both filters are plain attribute matches rather than a query
        language -- discovery here answers "what is available and what
        does it need", not "search"; Universal Search (M10A) is the
        surface for the latter.
        """
        result = tuple(self._capabilities.values())
        if kind is not None:
            result = tuple(c for c in result if c.kind == kind)
        if required_permission is not None:
            result = tuple(c for c in result if required_permission in c.permissions)
        return result

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._capabilities)

    def __len__(self) -> int:
        return len(self._capabilities)

    def snapshot(self) -> tuple[dict[str, object], ...]:
        """Serializable form for the REST/status surface -- the same
        "one plain-dict snapshot per registered thing" shape
        ``PluginRegistry.snapshot()`` already returns."""
        return tuple(
            {
                "name": c.name,
                "version": c.version,
                "kind": c.kind,
                "description": c.description,
                "permissions": list(c.permissions),
                "metadata": dict(c.metadata),
            }
            for c in self._capabilities.values()
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    @staticmethod
    def _validate(capability: MCPCapability) -> None:
        if not capability.name.strip():
            raise MCPCapabilityError("Capability name must not be empty.")
        if capability.kind not in CAPABILITY_KINDS:
            raise MCPCapabilityError(
                f"Unknown capability kind {capability.kind!r}; "
                f"allowed: {sorted(CAPABILITY_KINDS)}"
            )
        unknown = sorted(set(capability.permissions) - PERMISSION_SCOPES)
        if unknown:
            raise MCPCapabilityError(
                f"Unknown permission scope(s) {unknown} on capability "
                f"{capability.name!r}; allowed: {sorted(PERMISSION_SCOPES)}"
            )
