"""OAuth2 strategy tests -- Milestone 11 Task Group E.

The authentication half: PKCE, the flow store's single-use ``state``,
the authorization URL, the token exchange, refresh, and the
client-credentials grant. These are the *authentication tests* the task
brief requires, and several of them are security tests -- the flow
store's replay refusal and the redaction of verifiers most of all.

The token endpoint is exercised twice over: through an injected poster
for the logic, and through a real ``aiohttp`` server for
``HttpxTokenPoster``, so neither the parsing nor the transport is taken
on trust.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from aiohttp import web

from jarvis.core.mcp.auth.credentials import AuthMethod, Credential, MCPAuthError
from jarvis.core.mcp.auth.oauth2 import (
    BoundOAuth2Strategy,
    ClientCredentialsStrategy,
    HttpxTokenPoster,
    OAuth2AuthorizationCodeStrategy,
    OAuthFlowError,
    OAuthFlowStore,
    build_authorization_url,
    generate_pkce_verifier,
    pkce_challenge,
    register_oauth_strategies,
)
from jarvis.core.mcp.auth.strategies import build_default_strategy_registry


class _Poster:
    """Records what was posted and replies with a canned token body."""

    def __init__(self, payload: dict | None = None, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._payload = payload or {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "expires_in": 3600,
            "scope": "vendor.read vendor.send",
        }
        self._fail = fail

    async def __call__(self, url: str, form: dict) -> dict:
        self.calls.append((url, dict(form)))
        if self._fail:
            raise MCPAuthError("token endpoint refused")
        return self._payload


# --- PKCE -----------------------------------------------------------------------


def test_a_verifier_is_within_the_rfc_length_range() -> None:
    verifier = generate_pkce_verifier()
    assert 43 <= len(verifier) <= 128


def test_verifiers_are_unique() -> None:
    assert len({generate_pkce_verifier() for _ in range(50)}) == 50


def test_the_challenge_is_unpadded_base64url_sha256() -> None:
    """Several authorization servers reject the padding, which is why
    the '=' is stripped rather than left on."""
    verifier = "a" * 64
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )

    challenge = pkce_challenge(verifier)

    assert challenge == expected
    assert "=" not in challenge


# --- flow store -----------------------------------------------------------------


def _store(**kwargs) -> OAuthFlowStore:
    return OAuthFlowStore(**kwargs)


def _start(store: OAuthFlowStore, provider_id: str = "acme"):
    return store.start(
        provider_id,
        client_id="client-1",
        redirect_uri="https://app.test/callback",
        token_url="https://auth.test/token",
        scopes=("vendor.read",),
    )


def test_a_flow_carries_a_verifier_and_a_random_state() -> None:
    store = _store()
    first = _start(store)
    second = _start(store)

    assert first.state != second.state
    assert first.code_verifier != second.code_verifier
    assert len(store) == 2


def test_a_flow_can_be_consumed_once() -> None:
    """Single-use: an authorization code is single-use at the vendor
    too, and a store that let one be presented twice would invite the
    race."""
    store = _store()
    flow = _start(store)

    assert store.consume(flow.state).state == flow.state
    with pytest.raises(OAuthFlowError, match="already-used"):
        store.consume(flow.state)


def test_an_unknown_state_is_refused() -> None:
    with pytest.raises(OAuthFlowError, match="Unknown or already-used"):
        _store().consume("not-a-real-state")


def test_an_expired_flow_is_refused() -> None:
    store = _store(ttl_seconds=-1.0)
    flow = _start(store)

    with pytest.raises(OAuthFlowError, match="expired"):
        store.consume(flow.state)


def test_pruning_drops_expired_flows() -> None:
    store = _store(ttl_seconds=-1.0)
    _start(store)
    assert store.prune() == 1


def test_a_flow_redacts_its_secrets_on_repr() -> None:
    """A stray log line rendering a flow must not print the verifier
    that protects the exchange."""
    flow = _start(_store())

    rendered = repr(flow)

    assert flow.code_verifier not in rendered
    assert flow.state not in rendered
    assert "redacted" in rendered
    assert "acme" in rendered  # the non-secret parts still identify it


def test_pending_for_counts_without_exposing_flows() -> None:
    store = _store()
    _start(store, "acme")
    _start(store, "acme")
    _start(store, "other")

    assert store.pending_for("acme") == 2


# --- authorization URL ----------------------------------------------------------


def test_the_authorization_url_carries_pkce_and_state() -> None:
    flow = _start(_store())

    url = build_authorization_url("https://auth.test/authorize", flow)
    params = parse_qs(urlparse(url).query)

    assert params["response_type"] == ["code"]
    assert params["client_id"] == ["client-1"]
    assert params["state"] == [flow.state]
    assert params["code_challenge"] == [pkce_challenge(flow.code_verifier)]
    assert params["code_challenge_method"] == ["S256"]
    assert params["scope"] == ["vendor.read"]


def test_the_authorization_url_never_carries_the_verifier() -> None:
    """Sending it would defeat the exchange it protects."""
    flow = _start(_store())
    assert flow.code_verifier not in build_authorization_url("https://auth.test/authorize", flow)


def test_vendor_specific_params_are_merged() -> None:
    """Google needs access_type=offline to issue a refresh token at all
    -- the kind of vendor quirk that belongs in data."""
    flow = _start(_store())

    url = build_authorization_url(
        "https://auth.test/authorize", flow, extra_params={"access_type": "offline"}
    )

    assert parse_qs(urlparse(url).query)["access_type"] == ["offline"]


def test_an_authorize_url_with_an_existing_query_is_extended_not_broken() -> None:
    flow = _start(_store())
    url = build_authorization_url("https://auth.test/authorize?tenant=acme", flow)

    params = parse_qs(urlparse(url).query)
    assert params["tenant"] == ["acme"]
    assert params["state"] == [flow.state]


# --- authorization-code exchange -----------------------------------------------


@pytest.mark.asyncio
async def test_the_code_exchange_posts_every_required_field() -> None:
    poster = _Poster()
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=poster)

    credential = await strategy.authenticate(
        "acme",
        {
            "code": "auth-code",
            "code_verifier": "verifier",
            "redirect_uri": "https://app.test/callback",
            "client_id": "client-1",
            "client_secret": "shh",
            "token_url": "https://auth.test/token",
        },
    )

    url, form = poster.calls[0]
    assert url == "https://auth.test/token"
    assert form["grant_type"] == "authorization_code"
    assert form["code_verifier"] == "verifier"
    assert form["client_secret"] == "shh"
    assert credential.access_token == "at-1"
    assert credential.refresh_token == "rt-1"
    assert credential.method is AuthMethod.OAUTH2


@pytest.mark.asyncio
async def test_expires_in_becomes_an_absolute_expiry() -> None:
    """A relative lifetime is only meaningful next to the moment it was
    issued, so it is converted at the boundary."""
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=_Poster())

    credential = await strategy.authenticate(
        "acme",
        {
            "code": "c",
            "code_verifier": "v",
            "redirect_uri": "r",
            "client_id": "i",
            "token_url": "https://auth.test/token",
        },
    )

    assert credential.expires_at is not None
    remaining = credential.seconds_until_expiry()
    assert remaining is not None and 3000 < remaining <= 3600


@pytest.mark.asyncio
async def test_granted_scopes_come_from_the_response_not_the_request() -> None:
    """A vendor may grant fewer scopes than were asked for, and the
    credential must record what was actually granted."""
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=_Poster())

    credential = await strategy.authenticate(
        "acme",
        {
            "code": "c",
            "code_verifier": "v",
            "redirect_uri": "r",
            "client_id": "i",
            "token_url": "https://auth.test/token",
            "scopes": ["vendor.everything"],
        },
    )

    assert credential.scopes == ("vendor.read", "vendor.send")


@pytest.mark.asyncio
async def test_a_missing_exchange_field_is_refused_before_any_request() -> None:
    poster = _Poster()
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=poster)

    with pytest.raises(MCPAuthError, match="missing"):
        await strategy.authenticate("acme", {"code": "c"})

    assert poster.calls == []


@pytest.mark.asyncio
async def test_a_token_response_with_no_access_token_is_refused() -> None:
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=_Poster({"token_type": "bearer"}))

    with pytest.raises(MCPAuthError, match="no access_token"):
        await strategy.authenticate(
            "acme",
            {
                "code": "c",
                "code_verifier": "v",
                "redirect_uri": "r",
                "client_id": "i",
                "token_url": "https://auth.test/token",
            },
        )


@pytest.mark.asyncio
async def test_the_unbound_strategy_refuses_to_guess_a_refresh_endpoint() -> None:
    """A Credential carries no token URL on purpose -- that is
    configuration, not secret material -- so refusing beats inventing
    one."""
    strategy = OAuth2AuthorizationCodeStrategy(token_poster=_Poster())

    with pytest.raises(MCPAuthError, match="token endpoint"):
        await strategy.refresh(Credential(provider_id="acme", method=AuthMethod.OAUTH2))


# --- bound strategy: refresh and revoke ----------------------------------------


def _bound(poster: _Poster, **kwargs) -> BoundOAuth2Strategy:
    defaults = {
        "token_url": "https://auth.test/token",
        "client_id": "client-1",
        "client_secret": "shh",
        "token_poster": poster,
    }
    defaults.update(kwargs)
    return BoundOAuth2Strategy(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_bound_strategy_refreshes() -> None:
    poster = _Poster({"access_token": "at-2", "expires_in": 60})
    credential = Credential(
        provider_id="acme",
        method=AuthMethod.OAUTH2,
        access_token="at-1",
        refresh_token="rt-1",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    refreshed = await _bound(poster).refresh(credential)

    _, form = poster.calls[0]
    assert form["grant_type"] == "refresh_token"
    assert form["refresh_token"] == "rt-1"
    assert refreshed.access_token == "at-2"


@pytest.mark.asyncio
async def test_a_refresh_that_returns_no_new_refresh_token_keeps_the_old_one() -> None:
    """Vendors routinely omit it; dropping it would make the *second*
    refresh fail with nothing to explain it."""
    poster = _Poster({"access_token": "at-2", "expires_in": 60})
    credential = Credential(
        provider_id="acme",
        method=AuthMethod.OAUTH2,
        access_token="at-1",
        refresh_token="rt-1",
    )

    refreshed = await _bound(poster).refresh(credential)

    assert refreshed.refresh_token == "rt-1"
    assert refreshed.is_refreshable


@pytest.mark.asyncio
async def test_refreshing_without_a_refresh_token_is_refused() -> None:
    with pytest.raises(MCPAuthError, match="no refresh token"):
        await _bound(_Poster()).refresh(
            Credential(provider_id="acme", method=AuthMethod.OAUTH2, access_token="at-1")
        )


@pytest.mark.asyncio
async def test_revoke_tells_the_vendor_then_clears_locally() -> None:
    poster = _Poster({})
    strategy = _bound(poster, revoke_url="https://auth.test/revoke")
    credential = Credential(
        provider_id="acme", method=AuthMethod.OAUTH2, access_token="at-1", refresh_token="rt-1"
    )

    revoked = await strategy.revoke(credential)

    assert poster.calls[0][0] == "https://auth.test/revoke"
    assert revoked.revoked is True
    assert revoked.access_token == ""
    assert revoked.refresh_token == ""


@pytest.mark.asyncio
async def test_a_failed_remote_revoke_still_clears_the_local_token() -> None:
    """A credential JARVIS cannot present is a credential JARVIS cannot
    misuse -- so the local clear happens either way."""
    strategy = _bound(_Poster(fail=True), revoke_url="https://auth.test/revoke")

    revoked = await strategy.revoke(
        Credential(provider_id="acme", method=AuthMethod.OAUTH2, access_token="at-1")
    )

    assert revoked.revoked is True
    assert revoked.access_token == ""


# --- client credentials ---------------------------------------------------------


@pytest.mark.asyncio
async def test_client_credentials_exchanges_without_a_user() -> None:
    poster = _Poster({"access_token": "at-m2m", "expires_in": 900})
    strategy = ClientCredentialsStrategy(token_poster=poster)

    credential = await strategy.authenticate(
        "acme",
        {
            "token_url": "https://auth.test/token",
            "client_id": "svc",
            "client_secret": "shh",
            "scopes": ["vendor.admin"],
        },
    )

    _, form = poster.calls[0]
    assert form["grant_type"] == "client_credentials"
    assert form["scope"] == "vendor.admin"
    assert credential.method is AuthMethod.CLIENT_CREDENTIALS
    assert credential.access_token == "at-m2m"


@pytest.mark.asyncio
async def test_client_credentials_refresh_re_authenticates() -> None:
    """There is no refresh token in this grant, so 'refresh' really is a
    fresh authentication -- which is genuinely refreshing."""
    poster = _Poster({"access_token": "at-2", "expires_in": 900})
    strategy = ClientCredentialsStrategy(
        token_poster=poster,
        token_url="https://auth.test/token",
        client_id="svc",
        client_secret="shh",
    )

    refreshed = await strategy.refresh(
        Credential(provider_id="acme", method=AuthMethod.CLIENT_CREDENTIALS, access_token="at-1")
    )

    assert refreshed.access_token == "at-2"


@pytest.mark.asyncio
async def test_client_credentials_without_configuration_is_refused() -> None:
    strategy = ClientCredentialsStrategy(token_poster=_Poster())

    with pytest.raises(MCPAuthError, match="requires token_url"):
        await strategy.authenticate("acme", {})


# --- registry integration -------------------------------------------------------


def test_registering_closes_task_group_ds_deferral() -> None:
    """M10.5 shipped the vocabulary with both methods unsupported and
    said the milestone that built them would call register() and change
    nothing else. This is that call."""
    registry = build_default_strategy_registry()
    assert not registry.supports(AuthMethod.OAUTH2)

    register_oauth_strategies(registry)

    assert registry.supports(AuthMethod.OAUTH2)
    assert registry.supports(AuthMethod.CLIENT_CREDENTIALS)
    assert set(registry.supported_methods) >= {"oauth2", "client_credentials"}


def test_describe_reports_both_grants_as_supported_and_refreshable() -> None:
    registry = build_default_strategy_registry()
    register_oauth_strategies(registry)

    described = {row["method"]: row for row in registry.describe()}

    assert described["oauth2"]["supported"] is True
    assert described["oauth2"]["refreshable"] is True
    assert described["client_credentials"]["supported"] is True


# --- the real token poster ------------------------------------------------------


@pytest.mark.asyncio
async def test_the_httpx_poster_form_encodes_and_parses(aiohttp_server) -> None:
    seen: list[dict] = []

    async def handler(request: web.Request) -> web.Response:
        seen.append(dict(await request.post()))
        return web.json_response({"access_token": "at-real", "expires_in": 120})

    app = web.Application()
    app.router.add_post("/token", handler)
    server = await aiohttp_server(app)

    payload = await HttpxTokenPoster()(
        str(server.make_url("/token")), {"grant_type": "authorization_code", "code": "c"}
    )

    assert payload["access_token"] == "at-real"
    assert seen[0]["grant_type"] == "authorization_code"


@pytest.mark.asyncio
async def test_the_httpx_poster_surfaces_the_vendor_error_description(aiohttp_server) -> None:
    async def handler(_request: web.Request) -> web.Response:
        return web.json_response(
            {"error": "invalid_grant", "error_description": "code already redeemed"}, status=400
        )

    app = web.Application()
    app.router.add_post("/token", handler)
    server = await aiohttp_server(app)

    with pytest.raises(MCPAuthError, match="code already redeemed"):
        await HttpxTokenPoster()(str(server.make_url("/token")), {"grant_type": "x"})


@pytest.mark.asyncio
async def test_an_unreachable_token_endpoint_is_reported_as_such() -> None:
    with pytest.raises(MCPAuthError, match="unreachable"):
        await HttpxTokenPoster(timeout_seconds=1.0)("http://127.0.0.1:9/token", {})
