"""Reference examples -- Milestone 10.5 Task Group E, deliverable 4.

**Entirely self-contained.** Nothing here opens a socket, spawns a
process, reads a credential from the environment, or names a real
service. The example transport answers from an in-memory dict; the
example auth strategy mints a local token. They exist to be read, run
in a test, and copied -- not to connect to anything.

**Why examples live in ``src/`` rather than ``docs/``.** A code sample
in a document rots the moment an API changes and nothing notices. These
are imported by ``tests/unit/test_mcp_sdk_examples.py``, so the moment
the SDK's shape changes, the examples fail with it. That is the whole
point: the documentation-that-compiles half of deliverable 4 and 7.

A provider author's fastest path is to copy :func:`example_provider`
and change the strings.
"""

from __future__ import annotations

from typing import Any

from jarvis.core.interfaces.mcp import MCPCapability, MCPTransportError
from jarvis.core.mcp.auth.credentials import AuthMethod, Credential
from jarvis.core.mcp.negotiation import PROTOCOL_VERSION
from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata
from jarvis.core.mcp.sdk.builders import (
    CapabilityBuilder,
    ConfigBuilder,
    ProviderBuilder,
    TransportBuilder,
)

EXAMPLE_PROVIDER_ID = "example"
EXAMPLE_TRANSPORT_TYPE = "in_process"


# ---------------------------------------------------------------------------
# Example capability
# ---------------------------------------------------------------------------
def example_capability() -> MCPCapability:
    """A minimal, valid capability built through the SDK."""
    return (
        CapabilityBuilder("example.echo")
        .kind("tool")
        .describe("Echoes the text it is given back to the caller.")
        .with_permission("agent_tools")
        .with_metadata(input_schema={"text": "string"})
        .build()
    )


async def example_capability_invoker(params: dict[str, Any]) -> dict[str, Any]:
    """The coroutine an exposed capability binds to. Pure function of
    its input -- no I/O, so it is safe to run anywhere."""
    return {"echoed": str(params.get("text", ""))}


# ---------------------------------------------------------------------------
# Example provider + configuration
# ---------------------------------------------------------------------------
def example_provider() -> ProviderMetadata:
    """The declaration a provider author copies and edits."""
    return (
        ProviderBuilder("Example Provider")
        .version("1.0.0")
        .author("JARVIS SDK")
        .describe("A self-contained reference provider. Connects to nothing.")
        .transport(EXAMPLE_TRANSPORT_TYPE)
        .with_capability(example_capability())
        .with_permission("agent_tools")
        .with_tag("example", "reference")
        .build()
    )


def example_config() -> ProviderConfig:
    """Settings for the example provider, assembled by composing the
    transport builder into the config builder."""
    transport = TransportBuilder(EXAMPLE_TRANSPORT_TYPE).option("client_id", "example-client")
    return (
        ConfigBuilder()
        .from_transport(transport)
        .reconnect(max_attempts=2, backoff_seconds=0.1)
        .heartbeat(enabled=True)
        .build(example_provider())
    )


# ---------------------------------------------------------------------------
# Example transport
# ---------------------------------------------------------------------------
class ExampleTransport:
    """A transport that answers from memory.

    Satisfies :class:`~jarvis.core.interfaces.mcp.IMCPTransport`
    structurally, with no base class -- the same way every real
    transport does. Useful as a template and as a test double that
    exercises the real client runtime without a peer.

    **This is not a sixth transport type.** ``TRANSPORT_TYPES`` is
    closed, and an integration author configures one of the five rather
    than adding another; the SDK deliberately gives no way to widen that
    set. This class reuses ``in_process`` -- the honest name for direct
    in-memory dispatch -- and stands in for the shipped
    ``InProcessTransport``, which needs a live ``MCPServerRuntime``
    behind it. Register it where that runtime is not wired (a test, or a
    scratch registry); in a real container the shipped one is already
    registered under the same key and should stay that way.
    """

    transport_type = EXAMPLE_TRANSPORT_TYPE

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._connected:
            raise MCPTransportError(f"example: cannot call {method!r} while disconnected.")
        payload = params or {}

        if method == "initialize":
            return {"server_id": "example-peer", "agreed_version": PROTOCOL_VERSION}
        if method == "capabilities/list":
            capability = example_capability()
            return {
                "capabilities": [
                    {
                        "name": capability.name,
                        "version": capability.version,
                        "kind": capability.kind,
                        "description": capability.description,
                        "permissions": list(capability.permissions),
                        "metadata": dict(capability.metadata),
                    }
                ]
            }
        if method == "capabilities/call":
            return {"result": await example_capability_invoker(payload.get("arguments") or {})}
        if method == "ping":
            return {"pong": True, "server_id": "example-peer"}
        raise MCPTransportError(f"example: unknown method {method!r}.")


def build_example_transport(config: dict[str, Any]) -> ExampleTransport:
    """Factory in the shape ``TransportFactoryRegistry.register``
    expects."""
    return ExampleTransport(config)


# ---------------------------------------------------------------------------
# Example authentication strategy
# ---------------------------------------------------------------------------
class ExampleAuthStrategy:
    """A local, self-contained auth strategy.

    Mints a token locally rather than calling an issuer, so it
    demonstrates the ``IAuthStrategy`` shape -- including a *working*
    refresh, which the shipped static strategies deliberately refuse --
    without any network access or real secret.

    It claims ``BEARER_TOKEN`` because that is what it honestly issues.
    The platform already ships a strategy for that method, so
    registering this one needs ``replace=True``::

        strategies.register(ExampleAuthStrategy(), replace=True)

    That is the intended shape of the collision, not a wart: the
    registry refusing a silent override is the behaviour under test.
    Claiming an unregistered method such as ``OAUTH2`` would make the
    example run without ``replace``, at the cost of reporting an OAuth
    flow this class does not implement -- which is precisely the
    simulated functionality the project forbids.
    """

    method = AuthMethod.BEARER_TOKEN

    def __init__(self) -> None:
        self._counter = 0

    def _mint(self, provider_id: str) -> str:
        self._counter += 1
        return f"example-token-{provider_id}-{self._counter}"

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        return Credential(
            provider_id=provider_id,
            method=self.method,
            access_token=request.get("token") or self._mint(provider_id),
            refresh_token=f"example-refresh-{provider_id}",
            scopes=tuple(request.get("scopes") or ("example:read",)),
            account_id=str(request.get("account_id") or "example-account"),
        )

    async def refresh(self, credential: Credential) -> Credential:
        return credential.with_refreshed(self._mint(credential.provider_id))

    async def revoke(self, credential: Credential) -> Credential:
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return credential.is_valid() and credential.has_access_token
