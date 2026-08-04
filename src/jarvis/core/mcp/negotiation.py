"""Capability negotiation -- Milestone 10.5 Task Group A, deliverable 5.

Pure functions over plain data: no I/O, no transport, no permission
*store* access (the caller passes the already-resolved grant set in).
That keeps negotiation exhaustively unit-testable without a connection,
and keeps the one place that decides "can these two peers talk, and
about what" free of any dependency on *how* they are connected.

Three questions, answered in order:

1. **Version compatibility** -- do the peers share a protocol version?
   :func:`negotiate_version` picks the newest version *both* support,
   which is the graceful fallback: a peer offering only an older shared
   version still connects, on that older version, rather than being
   rejected outright.
2. **Capability compatibility** -- is each offered capability's *kind*
   one this platform understands? An unknown kind is rejected
   individually, never fatally.
3. **Permission compatibility** -- are the scopes a capability declares
   actually granted? Ungranted capabilities are dropped from the
   negotiated set with a recorded reason, and the connection still
   succeeds with whatever remains. Least-privilege by construction: a
   capability is excluded unless its scopes were explicitly granted.

A failure at step 1 fails the whole negotiation (there is no shared
language to continue in); failures at steps 2 and 3 are per-capability
and never fail the connection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jarvis.core.interfaces.mcp import CAPABILITY_KINDS

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    from jarvis.core.interfaces.mcp import MCPCapability

#: Protocol versions this platform speaks, newest first. Date-based, per
#: the MCP specification's own versioning convention. Task Group A
#: implements the negotiation *mechanism*; wire-level conformance to a
#: published revision is verified when the first network transport ships.
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = ("2025-06-18", "2025-03-26")

#: The version JARVIS offers first.
PROTOCOL_VERSION: str = SUPPORTED_PROTOCOL_VERSIONS[0]


@dataclass(frozen=True, slots=True)
class NegotiationResult:
    """Outcome of one negotiation. ``succeeded`` is derived from
    ``agreed_version`` rather than stored separately, so the two can
    never disagree."""

    agreed_version: str = ""
    capabilities: tuple[MCPCapability, ...] = ()
    rejected: tuple[tuple[str, str], ...] = ()  # (capability_name, reason)
    failure_reason: str = ""

    @property
    def succeeded(self) -> bool:
        return bool(self.agreed_version)

    @property
    def capability_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.capabilities)


def negotiate_version(
    local_versions: Sequence[str] = SUPPORTED_PROTOCOL_VERSIONS,
    remote_versions: Sequence[str] = (),
) -> str | None:
    """Newest version both sides support, or ``None``.

    "Newest" follows *local_versions*' own order rather than sorting the
    strings: the ordering of supported versions is a deliberate
    preference list, and string-sorting date-based versions would only
    coincidentally agree with it.
    """
    remote = set(remote_versions)
    for version in local_versions:
        if version in remote:
            return version
    return None


def negotiate(
    offered: Iterable[MCPCapability],
    *,
    remote_versions: Sequence[str],
    granted_scopes: Collection[str],
    local_versions: Sequence[str] = SUPPORTED_PROTOCOL_VERSIONS,
) -> NegotiationResult:
    """Negotiate a connection against *offered* capabilities.

    *granted_scopes* is the set of permission scopes already granted for
    this peer -- resolved by the caller from the existing
    ``PermissionModel``, so this function never reaches into a
    permission store and stays a pure function of its arguments.
    """
    agreed = negotiate_version(local_versions, remote_versions)
    if agreed is None:
        return NegotiationResult(
            failure_reason=(
                f"No shared protocol version. Local: {list(local_versions)}; "
                f"remote: {list(remote_versions)}."
            )
        )

    accepted: list[MCPCapability] = []
    rejected: list[tuple[str, str]] = []
    granted = set(granted_scopes)

    for capability in offered:
        if capability.kind not in CAPABILITY_KINDS:
            rejected.append((capability.name, f"Unsupported capability kind {capability.kind!r}."))
            continue
        missing = sorted(set(capability.permissions) - granted)
        if missing:
            rejected.append((capability.name, f"Permission(s) not granted: {missing}."))
            continue
        accepted.append(capability)

    return NegotiationResult(
        agreed_version=agreed,
        capabilities=tuple(accepted),
        rejected=tuple(rejected),
    )


@dataclass(frozen=True, slots=True)
class HandshakeRequest:
    """What a client sends on connect. Serialized by the transport;
    never touches the wire format itself."""

    client_id: str
    protocol_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HandshakeResponse:
    """What a server replies with. ``agreed_version`` empty means the
    handshake failed -- same derived-``succeeded`` discipline as
    :class:`NegotiationResult`."""

    server_id: str
    agreed_version: str = ""
    protocol_versions: tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS
    failure_reason: str = ""

    @property
    def succeeded(self) -> bool:
        return bool(self.agreed_version)
