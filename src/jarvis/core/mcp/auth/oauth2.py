"""OAuth2 strategies -- Milestone 11 Task Group E.

Closes the deferral ``core/mcp/auth/strategies.py`` recorded in Task
Group D: *"``oauth2`` and ``client_credentials`` are deliberately not
implemented here. Both require an authorization server, a redirect URI
and a callback endpoint to complete a flow, and this task group
explicitly ships no login endpoint and no OAuth callback."* This
milestone ships all three, so both strategies land here and register
into the **existing** :class:`AuthStrategyRegistry` -- no second auth
framework, no second credential model, no second store. The registry's
own note anticipated exactly this: *"the milestone that builds them
calls ``register(...)`` here and nothing else changes."*

**PKCE is mandatory, not optional.** :class:`OAuthFlowStore` generates a
verifier for every authorization-code flow and the strategy always sends
the challenge. RFC 7636 was written for public clients, but it costs one
hash for a confidential one and it closes authorization-code
interception outright -- and a desktop application distributing a client
secret is not meaningfully confidential anyway.

**``state`` is the CSRF defence and the flow's only key.** It is
generated with ``secrets``, single-use, and expires. The callback
endpoint cannot require a Bearer token (a browser redirect carries no
Authorization header), so ``state`` is what proves the response belongs
to a flow this process started -- which is why consuming it is atomic
and why an unknown or replayed value is refused rather than tolerated.

**Secrets stay out of the flow record.** :class:`OAuthFlow` holds the
PKCE verifier (a secret for the duration of one flow, and unavoidable)
and never the client secret or a token. It redacts on ``repr`` for the
same reason :class:`Credential` does.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.auth.credentials import AuthMethod, Credential, MCPAuthError

if TYPE_CHECKING:
    from collections.abc import Sequence

_logger = get_logger("jarvis.core.mcp.auth.oauth2")

#: How long an unfinished authorization flow stays valid. Ten minutes is
#: long enough for a user to read a consent screen and short enough that
#: an abandoned flow is not a lingering credential-shaped hole.
DEFAULT_FLOW_TTL_SECONDS = 600.0

#: Refresh this far before expiry rather than after. A token that
#: expires mid-request produces a confusing 401 from the vendor; a
#: little early costs one extra round trip an hour.
DEFAULT_REFRESH_LEEWAY_SECONDS = 120.0

_REDACTED = "***redacted***"


class OAuthFlowError(MCPAuthError):
    """An authorization flow that cannot be started or completed."""


def generate_pkce_verifier() -> str:
    """A high-entropy code verifier (RFC 7636 §4.1).

    ``token_urlsafe(64)`` yields ~86 characters, inside the spec's
    43--128 range, from a CSPRNG. Not ``uuid4`` -- that is 122 bits with
    a documented structure, and this is a secret.
    """
    return secrets.token_urlsafe(64)


def pkce_challenge(verifier: str) -> str:
    """The S256 challenge for *verifier* (RFC 7636 §4.2).

    Base64url without padding, which the spec requires and which several
    authorization servers reject if you leave the ``=`` on.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass(slots=True)
class OAuthFlow:
    """One authorization-code flow in progress."""

    state: str
    provider_id: str
    client_id: str
    redirect_uri: str
    token_url: str
    code_verifier: str
    scopes: tuple[str, ...] = ()
    revoke_url: str = ""
    created_at: float = field(default_factory=time.monotonic)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return (
            f"OAuthFlow(state={_REDACTED!r}, provider_id={self.provider_id!r}, "
            f"client_id={self.client_id!r}, redirect_uri={self.redirect_uri!r}, "
            f"code_verifier={_REDACTED!r}, scopes={self.scopes!r})"
        )

    __str__ = __repr__

    def is_expired(self, *, ttl_seconds: float, now: float | None = None) -> bool:
        return (now or time.monotonic()) - self.created_at > ttl_seconds


class OAuthFlowStore:
    """In-flight authorization flows, keyed by ``state``.

    **Not a second credential store.** Nothing here survives a restart,
    nothing here is a token, and an entry lives for one browser round
    trip. ``CredentialStore`` owns anything durable; this owns the
    ten-minute gap between "open the consent screen" and "the browser
    came back".
    """

    def __init__(self, *, ttl_seconds: float = DEFAULT_FLOW_TTL_SECONDS) -> None:
        self._ttl = ttl_seconds
        self._flows: dict[str, OAuthFlow] = {}

    def start(
        self,
        provider_id: str,
        *,
        client_id: str,
        redirect_uri: str,
        token_url: str,
        scopes: Sequence[str] = (),
        revoke_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> OAuthFlow:
        self.prune()
        flow = OAuthFlow(
            state=secrets.token_urlsafe(32),
            provider_id=provider_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            token_url=token_url,
            code_verifier=generate_pkce_verifier(),
            scopes=tuple(scopes),
            revoke_url=revoke_url,
            metadata=dict(metadata or {}),
        )
        self._flows[flow.state] = flow
        _logger.info("OAuth flow started for provider {!r}.", provider_id)
        return flow

    def consume(self, state: str) -> OAuthFlow:
        """Take a flow out of the store, once.

        Removal happens before validation so a replayed ``state`` cannot
        be used even if the first attempt errored afterwards -- an
        authorization code is single-use at the vendor too, and a store
        that let one be presented twice would be inviting the race.
        """
        flow = self._flows.pop(state, None)
        if flow is None:
            raise OAuthFlowError(
                "Unknown or already-used authorization state. Start the flow again."
            )
        if flow.is_expired(ttl_seconds=self._ttl):
            raise OAuthFlowError(
                f"Authorization flow for {flow.provider_id!r} expired after "
                f"{self._ttl:.0f}s. Start it again."
            )
        return flow

    def prune(self) -> int:
        now = time.monotonic()
        stale = [s for s, f in self._flows.items() if f.is_expired(ttl_seconds=self._ttl, now=now)]
        for state in stale:
            self._flows.pop(state, None)
        return len(stale)

    def pending_for(self, provider_id: str) -> int:
        """How many flows are open for a provider. Used by diagnostics;
        never returns the flows themselves, which hold verifiers."""
        return sum(1 for flow in self._flows.values() if flow.provider_id == provider_id)

    def __len__(self) -> int:
        return len(self._flows)


def build_authorization_url(
    authorize_url: str,
    flow: OAuthFlow,
    *,
    extra_params: dict[str, str] | None = None,
) -> str:
    """The URL a user opens to grant consent.

    ``code_challenge_method=S256`` is always sent -- ``plain`` is in the
    RFC for constrained clients that cannot hash, which does not
    describe anything running Python.
    """
    params = {
        "response_type": "code",
        "client_id": flow.client_id,
        "redirect_uri": flow.redirect_uri,
        "state": flow.state,
        "code_challenge": pkce_challenge(flow.code_verifier),
        "code_challenge_method": "S256",
    }
    if flow.scopes:
        params["scope"] = " ".join(flow.scopes)
    params |= extra_params or {}
    separator = "&" if "?" in authorize_url else "?"
    return f"{authorize_url}{separator}{urlencode(params)}"


class OAuth2AuthorizationCodeStrategy:
    """The authorization-code grant, with PKCE.

    Satisfies ``IAuthStrategy`` structurally, like every other strategy
    here -- no base class, composition over inheritance.

    The HTTP client is injected as a callable rather than an
    ``httpx.AsyncClient`` so this class never owns a connection pool:
    the gateway owns egress, and a strategy holding its own pool would
    be a second egress path outside the audited one.
    """

    method = AuthMethod.OAUTH2

    def __init__(
        self,
        *,
        token_poster: TokenPoster | None = None,
        refresh_leeway_seconds: float = DEFAULT_REFRESH_LEEWAY_SECONDS,
    ) -> None:
        self._post = token_poster or HttpxTokenPoster()
        self._leeway = refresh_leeway_seconds

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        """Exchange an authorization code for tokens.

        *request* carries what the callback and the flow together
        produced: ``code``, ``code_verifier``, ``redirect_uri``,
        ``client_id``, ``token_url`` and optionally ``client_secret``.
        None of it is logged.
        """
        missing = [
            key
            for key in ("code", "code_verifier", "redirect_uri", "client_id", "token_url")
            if not str(request.get(key) or "").strip()
        ]
        if missing:
            raise MCPAuthError(
                f"oauth2 authentication for {provider_id!r} is missing {sorted(missing)}."
            )

        form = {
            "grant_type": "authorization_code",
            "code": str(request["code"]),
            "redirect_uri": str(request["redirect_uri"]),
            "client_id": str(request["client_id"]),
            "code_verifier": str(request["code_verifier"]),
        }
        secret = str(request.get("client_secret") or "")
        if secret:
            form["client_secret"] = secret

        payload = await self._post(str(request["token_url"]), form)
        return _credential_from_token_response(
            provider_id,
            payload,
            method=self.method,
            fallback_scopes=tuple(request.get("scopes") or ()),
            account_id=str(request.get("account_id") or ""),
        )

    async def refresh(self, credential: Credential) -> Credential:
        """Exchange the refresh token for a new access token.

        The token URL and client id travel in the credential's own
        ``scopes``-adjacent metadata? No -- they travel in *arguments*,
        because a ``Credential`` is deliberately free of endpoint
        configuration. :class:`RefreshableOAuth2Strategy` below binds
        them; this base refuses rather than guessing an endpoint.
        """
        raise MCPAuthError(
            f"Refreshing {credential.provider_id!r} needs its token endpoint and client "
            "id, which a Credential does not carry. Use the strategy bound to that "
            "provider's configuration (see IntegrationAuthBinder)."
        )

    async def revoke(self, credential: Credential) -> Credential:
        """Local revocation only in the base strategy.

        A remote revoke needs the vendor's revocation endpoint, which
        again is configuration rather than credential state. Clearing
        the local token is the part that is always correct and always
        safe -- a credential JARVIS cannot present is a credential
        JARVIS cannot misuse.
        """
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return credential.is_valid() and credential.has_access_token


class BoundOAuth2Strategy(OAuth2AuthorizationCodeStrategy):
    """An OAuth2 strategy that knows one provider's endpoints.

    The base strategy cannot refresh because a ``Credential`` carries no
    token URL and no client id -- deliberately, since those are
    deployment configuration and a credential is secret material. This
    subclass is constructed *per provider* by the integration layer,
    which does know them, so ``refresh`` and remote ``revoke`` become
    possible without widening the credential model.

    Registered per provider rather than globally: the shared
    ``AuthStrategyRegistry`` keeps the unbound strategy for the generic
    ``authenticate`` path, and the integration layer uses a bound one
    where an endpoint is required.
    """

    def __init__(
        self,
        *,
        token_url: str,
        client_id: str,
        client_secret: str = "",
        revoke_url: str = "",
        token_poster: TokenPoster | None = None,
        refresh_leeway_seconds: float = DEFAULT_REFRESH_LEEWAY_SECONDS,
    ) -> None:
        super().__init__(token_poster=token_poster, refresh_leeway_seconds=refresh_leeway_seconds)
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._revoke_url = revoke_url

    async def refresh(self, credential: Credential) -> Credential:
        if not credential.has_refresh_token:
            raise MCPAuthError(
                f"Credential for {credential.provider_id!r} has no refresh token. "
                "Re-authorize the integration."
            )
        form = {
            "grant_type": "refresh_token",
            "refresh_token": credential.refresh_token,
            "client_id": self._client_id,
        }
        if self._client_secret:
            form["client_secret"] = self._client_secret

        payload = await self._post(self._token_url, form)
        refreshed = _credential_from_token_response(
            credential.provider_id,
            payload,
            method=self.method,
            fallback_scopes=credential.scopes,
            account_id=credential.account_id,
        )
        # Vendors routinely omit the refresh token on a refresh; keeping
        # the existing one is what stops the second refresh failing.
        return credential.with_refreshed(
            refreshed.access_token,
            refresh_token=refreshed.refresh_token or None,
            expires_at=refreshed.expires_at,
            scopes=refreshed.scopes or None,
        )

    async def revoke(self, credential: Credential) -> Credential:
        """Tell the vendor, then clear locally.

        A failed remote revoke must never leave the local token usable,
        so the local clear happens either way -- the same posture
        ``MCPAuthManager.revoke`` already takes when a strategy raises.
        """
        if self._revoke_url and credential.has_access_token:
            try:
                await self._post(self._revoke_url, {"token": credential.access_token})
            except Exception as err:
                _logger.warning(
                    "Remote revoke for {!r} failed; clearing locally anyway: {}",
                    credential.provider_id,
                    err,
                )
        return credential.revoke()


class ClientCredentialsStrategy:
    """The client-credentials grant -- machine-to-machine, no user.

    The other half of Task Group D's deferral. No redirect, no consent
    screen, no PKCE (there is no user agent to intercept anything), and
    no refresh token: when the token expires you ask for another with
    the same client credentials, which is what :meth:`refresh` does.
    """

    method = AuthMethod.CLIENT_CREDENTIALS

    def __init__(
        self,
        *,
        token_poster: TokenPoster | None = None,
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
    ) -> None:
        self._post = token_poster or HttpxTokenPoster()
        self._token_url = token_url
        self._client_id = client_id
        self._client_secret = client_secret

    async def authenticate(self, provider_id: str, request: dict[str, Any]) -> Credential:
        token_url = str(request.get("token_url") or self._token_url)
        client_id = str(request.get("client_id") or self._client_id)
        client_secret = str(request.get("client_secret") or self._client_secret)
        if not (token_url and client_id and client_secret):
            raise MCPAuthError(
                f"client_credentials for {provider_id!r} requires token_url, client_id "
                "and client_secret."
            )
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        }
        scopes = tuple(request.get("scopes") or ())
        if scopes:
            form["scope"] = " ".join(scopes)

        payload = await self._post(token_url, form)
        return _credential_from_token_response(
            provider_id, payload, method=self.method, fallback_scopes=scopes
        )

    async def refresh(self, credential: Credential) -> Credential:
        """Re-authenticate with the same client credentials.

        There is no refresh token in this grant, so "refresh" is a fresh
        authentication -- which is genuinely refreshing, and saying so
        beats raising "not refreshable" for a method whose whole point
        is that it can renew itself unattended.
        """
        if not (self._token_url and self._client_id and self._client_secret):
            raise MCPAuthError(
                f"Cannot refresh {credential.provider_id!r}: this strategy was not "
                "constructed with client credentials."
            )
        return await self.authenticate(credential.provider_id, {"scopes": credential.scopes})

    async def revoke(self, credential: Credential) -> Credential:
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return credential.is_valid() and credential.has_access_token


# ---------------------------------------------------------------------------
# Token endpoint access
# ---------------------------------------------------------------------------
class TokenPoster:
    """How a strategy reaches a token endpoint.

    A Protocol-shaped callable rather than a client, so a test supplies
    a function and production supplies :class:`HttpxTokenPoster` --
    without either needing a fake ``httpx``.
    """

    async def __call__(self, url: str, form: dict[str, str]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError


class HttpxTokenPoster:
    """Posts a form-encoded token request over ``httpx``.

    Its own short-lived client rather than the gateway's pool: a token
    exchange happens once per hour at most, it must work before any
    integration is connected (so before the gateway is necessarily
    open), and keeping it out of the audited egress path means a token
    body can never land in a call audit.
    """

    def __init__(self, *, timeout_seconds: float = 20.0, verify: bool = True) -> None:
        self._timeout = timeout_seconds
        self._verify = verify

    async def __call__(self, url: str, form: dict[str, str]) -> dict[str, Any]:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self._timeout, verify=self._verify) as client:
                response = await client.post(
                    url,
                    data=form,
                    headers={"Accept": "application/json"},
                )
        except httpx.HTTPError as err:
            raise MCPAuthError(f"Token endpoint {url} unreachable: {err}") from err

        try:
            payload = response.json()
        except ValueError as err:
            raise MCPAuthError(
                f"Token endpoint {url} returned a non-JSON response (HTTP "
                f"{response.status_code})."
            ) from err

        if response.status_code >= 400 or not isinstance(payload, dict):
            detail = ""
            if isinstance(payload, dict):
                detail = str(payload.get("error_description") or payload.get("error") or "")
            raise MCPAuthError(
                f"Token endpoint refused the request (HTTP {response.status_code})"
                f"{f': {detail}' if detail else ''}."
            )
        return payload


def _credential_from_token_response(
    provider_id: str,
    payload: dict[str, Any],
    *,
    method: AuthMethod,
    fallback_scopes: tuple[str, ...] = (),
    account_id: str = "",
) -> Credential:
    """Build a :class:`Credential` from a token endpoint's JSON.

    ``expires_in`` is converted to an absolute ``expires_at`` here, at
    the boundary, so nothing downstream has to remember when the
    response arrived -- a relative lifetime is only meaningful next to
    the moment it was issued.
    """
    access_token = str(payload.get("access_token") or "")
    if not access_token:
        raise MCPAuthError(f"Token response for {provider_id!r} contained no access_token.")

    expires_at: datetime | None = None
    raw_expiry = payload.get("expires_in")
    if raw_expiry is not None:
        try:
            expires_at = datetime.now(UTC) + timedelta(seconds=float(raw_expiry))
        except (TypeError, ValueError):
            expires_at = None

    granted = payload.get("scope")
    scopes = tuple(str(granted).split()) if granted else fallback_scopes

    return Credential(
        provider_id=provider_id,
        method=method,
        access_token=access_token,
        refresh_token=str(payload.get("refresh_token") or ""),
        expires_at=expires_at,
        scopes=scopes,
        account_id=account_id,
    )


def register_oauth_strategies(
    registry: Any,
    *,
    token_poster: TokenPoster | None = None,
    replace: bool = True,
) -> None:
    """Add both grants to an existing :class:`AuthStrategyRegistry`.

    The one function Task Group D's docstring predicted: *"the milestone
    that builds them calls ``register(...)`` here and nothing else
    changes."* Nothing else changes.
    """
    registry.register(OAuth2AuthorizationCodeStrategy(token_poster=token_poster), replace=replace)
    registry.register(ClientCredentialsStrategy(token_poster=token_poster), replace=replace)
