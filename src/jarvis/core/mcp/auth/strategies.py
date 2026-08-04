"""Authentication strategies -- Milestone 10.5 Task Group D,
deliverable 1.

The seam a future authentication method plugs into. One strategy per
:class:`~jarvis.core.mcp.auth.credentials.AuthMethod`, registered by
method name, so the manager never branches on how a credential was
obtained -- the same registry shape ``TransportFactoryRegistry`` (Task
Group B) and ``MCPProviderRegistry`` (Task Group C) already use.

**What ships and what does not, precisely.**

- :class:`StaticTokenStrategy` handles ``api_key``, ``bearer_token``
  and ``personal_access_token`` -- genuinely complete, because those
  methods *have* no flow: the secret is supplied, validated and stored.
  Nothing about them is provider-specific.
- :class:`NoAuthStrategy` handles ``none``, the real state a local
  stdio peer occupies.
- ``oauth2`` and ``client_credentials`` are **deliberately not
  implemented here.** Both require an authorization server, a redirect
  URI and a callback endpoint to complete a flow, and this task group
  explicitly ships no login endpoint and no OAuth callback. Registering
  a half-flow that cannot actually complete would be worse than
  registering nothing: :meth:`AuthStrategyRegistry.get` reports the
  method as unsupported, naming what is missing, and the vocabulary
  already includes both so the milestone that builds them changes no
  consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.auth.credentials import (
    STATIC_METHODS,
    AuthMethod,
    Credential,
    MCPAuthError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = get_logger("jarvis.core.mcp.auth.strategies")


class UnsupportedAuthMethodError(MCPAuthError):
    """The method is in the vocabulary but no strategy implements it."""


@runtime_checkable
class IAuthStrategy(Protocol):
    """How one authentication method obtains and maintains a credential.

    Every method returns a *new* ``Credential`` rather than mutating one,
    matching the frozen model -- a failed refresh cannot leave a
    half-updated credential behind.
    """

    method: AuthMethod

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        """Produce a credential from *request*. Raises
        :class:`MCPAuthError` if the request is unusable."""
        ...

    async def refresh(self, credential: Credential) -> Credential:
        """Exchange a refresh token for a fresh credential."""
        ...

    async def revoke(self, credential: Credential) -> Credential:
        """Invalidate the credential, locally and (where a method
        supports it) remotely."""
        ...

    def validate(self, credential: Credential) -> bool:
        """Cheap local check -- never a network call."""
        ...


class NoAuthStrategy:
    """For peers that need no credential at all -- a local stdio
    subprocess, typically. Modelled explicitly so "needs nothing" is a
    real state rather than an empty credential standing in for one."""

    method = AuthMethod.NONE

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        return Credential(provider_id=provider_id, method=AuthMethod.NONE)

    async def refresh(self, credential: Credential) -> Credential:
        return credential

    async def revoke(self, credential: Credential) -> Credential:
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return not credential.revoked


class StaticTokenStrategy:
    """A single long-lived secret: API key, bearer token, or PAT.

    Complete rather than a stub -- these methods have no handshake. The
    only real work is refusing an empty secret loudly instead of storing
    a credential that will fail confusingly at first use.
    """

    def __init__(self, method: AuthMethod) -> None:
        if method not in STATIC_METHODS:
            raise MCPAuthError(
                f"{method.value!r} is not a static-token method; "
                f"expected one of {sorted(m.value for m in STATIC_METHODS)}."
            )
        self.method = method

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        token = str(request.get("token") or request.get("access_token") or "")
        if not token:
            raise MCPAuthError(
                f"{self.method.value} authentication for {provider_id!r} requires a "
                "'token' entry in the request."
            )
        return Credential(
            provider_id=provider_id,
            method=self.method,
            access_token=token,
            scopes=tuple(request.get("scopes") or ()),
            account_id=str(request.get("account_id") or ""),
            # A static secret has no issuer-declared expiry; a caller
            # may still set one to force periodic rotation.
            expires_at=request.get("expires_at"),
        )

    async def refresh(self, credential: Credential) -> Credential:
        """A static secret cannot be refreshed -- it is rotated by
        re-authenticating with a new one. Saying so beats returning the
        same credential and letting the caller believe it renewed."""
        raise MCPAuthError(
            f"{self.method.value} credentials cannot be refreshed; "
            "re-authenticate with a new token instead."
        )

    async def revoke(self, credential: Credential) -> Credential:
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return credential.is_valid() and credential.has_access_token


class AuthStrategyRegistry:
    """Maps an :class:`AuthMethod` to the strategy implementing it."""

    def __init__(self) -> None:
        self._strategies: dict[AuthMethod, IAuthStrategy] = {}

    def register(self, strategy: IAuthStrategy, *, replace: bool = False) -> None:
        if strategy.method in self._strategies and not replace:
            raise MCPAuthError(
                f"A strategy for {strategy.method.value!r} is already registered; "
                "pass replace=True to override it deliberately."
            )
        self._strategies[strategy.method] = strategy
        _logger.info("MCP auth strategy registered: {}", strategy.method.value)

    def unregister(self, method: AuthMethod) -> bool:
        return self._strategies.pop(method, None) is not None

    def supports(self, method: AuthMethod) -> bool:
        return method in self._strategies

    def get(self, method: AuthMethod) -> IAuthStrategy:
        strategy = self._strategies.get(method)
        if strategy is None:
            raise UnsupportedAuthMethodError(
                f"No strategy is registered for {method.value!r}. "
                f"Supported: {sorted(m.value for m in self._strategies)}."
            )
        return strategy

    @property
    def supported_methods(self) -> tuple[str, ...]:
        return tuple(sorted(m.value for m in self._strategies))

    def describe(self) -> tuple[dict[str, Any], ...]:
        """Every method in the vocabulary and whether this build can
        actually perform it -- the same known-versus-registered honesty
        Task Group B's transport endpoint reports."""
        return tuple(
            {
                "method": method.value,
                "supported": method in self._strategies,
                "refreshable": method in {AuthMethod.OAUTH2, AuthMethod.CLIENT_CREDENTIALS},
            }
            for method in AuthMethod
        )


def build_default_strategy_registry(
    *, methods: Sequence[AuthMethod] | None = None
) -> AuthStrategyRegistry:
    """Every strategy this build ships.

    ``oauth2``/``client_credentials`` are absent by design -- see this
    module's docstring. The milestone that adds them calls
    ``register(...)`` here and nothing else changes.
    """
    registry = AuthStrategyRegistry()
    registry.register(NoAuthStrategy())
    for method in methods or sorted(STATIC_METHODS, key=lambda m: m.value):
        if method in STATIC_METHODS:
            registry.register(StaticTokenStrategy(method), replace=True)
    return registry
