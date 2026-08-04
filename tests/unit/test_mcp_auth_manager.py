"""Authentication manager, session and strategy tests -- Milestone 10.5
Task Group D, deliverables 1, 4, 5, 6, 7 and 8.

Permission assertions run against the *real* M9 ``PermissionModel`` on a
real temp-file store: the deliverable is that there is no second
permission system, so a fake one would prove nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from jarvis.core.events.event_bus import EventBus
from jarvis.core.events.events import MCPAuthStateChangedEvent
from jarvis.core.mcp.auth.credentials import (
    AuthMethod,
    Credential,
    MCPAuthError,
)
from jarvis.core.mcp.auth.manager import AUTH_ACTIONS, MCPAuthManager
from jarvis.core.mcp.auth.session import SessionState
from jarvis.core.mcp.auth.store import CredentialStore
from jarvis.core.mcp.auth.strategies import (
    AuthStrategyRegistry,
    NoAuthStrategy,
    StaticTokenStrategy,
    UnsupportedAuthMethodError,
    build_default_strategy_registry,
)
from jarvis.core.mcp.server import principal_for
from jarvis.core.plugins.permissions import PermissionModel

_TOKEN = "tok_SUPER_SECRET_VALUE"
_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


class _RefreshableStrategy:
    """A stand-in for the OAuth2 strategy a later milestone ships --
    enough to exercise the refresh/reconnect paths the framework owns."""

    method = AuthMethod.OAUTH2

    def __init__(self, *, fail_refresh: bool = False) -> None:
        self.fail_refresh = fail_refresh
        self.refresh_calls = 0

    async def authenticate(self, provider_id: str, request: dict) -> Credential:
        return Credential(
            provider_id=provider_id,
            method=AuthMethod.OAUTH2,
            access_token="access_1",
            refresh_token="refresh_1",
            expires_at=request.get("expires_at"),
            scopes=tuple(request.get("scopes") or ()),
        )

    async def refresh(self, credential: Credential) -> Credential:
        self.refresh_calls += 1
        if self.fail_refresh:
            raise MCPAuthError("refresh rejected by issuer")
        return credential.with_refreshed("access_2", expires_at=_NOW + timedelta(hours=1))

    async def revoke(self, credential: Credential) -> Credential:
        return credential.revoke()

    def validate(self, credential: Credential) -> bool:
        return credential.is_valid()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def permissions(bus: EventBus, tmp_path: Path) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "perm.json")


@pytest.fixture
def store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / "creds.json", secret_key=Fernet.generate_key().decode())


@pytest.fixture
def strategies() -> AuthStrategyRegistry:
    return build_default_strategy_registry()


@pytest.fixture
def manager(
    store: CredentialStore,
    strategies: AuthStrategyRegistry,
    permissions: PermissionModel,
    bus: EventBus,
) -> MCPAuthManager:
    return MCPAuthManager(store, strategies, permissions, event_bus=bus)


# --- Strategies -----------------------------------------------------------------


def test_default_registry_ships_static_methods_and_none(
    strategies: AuthStrategyRegistry,
) -> None:
    assert set(strategies.supported_methods) == {
        "api_key",
        "bearer_token",
        "personal_access_token",
        "none",
    }


def test_oauth_is_in_the_vocabulary_but_unsupported(
    strategies: AuthStrategyRegistry,
) -> None:
    """Registering a flow that cannot complete would be worse than
    registering none -- it is reported honestly instead."""
    described = {d["method"]: d for d in strategies.describe()}

    assert described["oauth2"]["supported"] is False
    assert described["oauth2"]["refreshable"] is True
    with pytest.raises(UnsupportedAuthMethodError, match="No strategy is registered"):
        strategies.get(AuthMethod.OAUTH2)


def test_duplicate_strategy_registration_is_refused(
    strategies: AuthStrategyRegistry,
) -> None:
    with pytest.raises(MCPAuthError, match="already registered"):
        strategies.register(NoAuthStrategy())
    strategies.register(NoAuthStrategy(), replace=True)


def test_static_strategy_rejects_a_non_static_method() -> None:
    with pytest.raises(MCPAuthError, match="not a static-token method"):
        StaticTokenStrategy(AuthMethod.OAUTH2)


@pytest.mark.asyncio
async def test_static_strategy_requires_a_token() -> None:
    with pytest.raises(MCPAuthError, match="requires a 'token'"):
        await StaticTokenStrategy(AuthMethod.API_KEY).authenticate("demo", {})


@pytest.mark.asyncio
async def test_static_strategy_refuses_to_pretend_it_refreshed() -> None:
    """Returning the same credential would let a caller believe it
    renewed an expired secret."""
    strategy = StaticTokenStrategy(AuthMethod.API_KEY)
    with pytest.raises(MCPAuthError, match="cannot be refreshed"):
        await strategy.refresh(Credential(provider_id="d", method=AuthMethod.API_KEY))


# --- Authenticate ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_stores_and_activates(manager: MCPAuthManager) -> None:
    credential = await manager.authenticate(
        "demo", AuthMethod.API_KEY, {"token": _TOKEN, "scopes": ["repo:read"]}
    )

    assert credential.access_token == _TOKEN
    assert manager.validate("demo") is True
    assert manager.session("demo").state is SessionState.ACTIVE
    assert manager.session("demo").granted_scopes == ("repo:read",)


@pytest.mark.asyncio
async def test_authenticate_failure_marks_the_session_failed(
    manager: MCPAuthManager,
) -> None:
    with pytest.raises(MCPAuthError):
        await manager.authenticate("demo", AuthMethod.API_KEY, {})  # no token

    session = manager.session("demo")
    assert session.state is SessionState.FAILED
    assert session.failure_count == 1
    assert manager.validate("demo") is False


@pytest.mark.asyncio
async def test_authenticate_with_an_unsupported_method_fails_loudly(
    manager: MCPAuthManager,
) -> None:
    with pytest.raises(UnsupportedAuthMethodError):
        await manager.authenticate("demo", AuthMethod.OAUTH2, {})


@pytest.mark.asyncio
async def test_no_auth_method_authenticates_without_a_token(
    manager: MCPAuthManager,
) -> None:
    """A local stdio peer needs no credential; that is a real state."""
    await manager.authenticate("local", AuthMethod.NONE, {})

    assert manager.validate("local") is True


# --- Refresh --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_replaces_the_access_token(
    store: CredentialStore, permissions: PermissionModel, bus: EventBus
) -> None:
    strategies = build_default_strategy_registry()
    strategies.register(_RefreshableStrategy())
    manager = MCPAuthManager(store, strategies, permissions, event_bus=bus)
    await manager.authenticate("demo", AuthMethod.OAUTH2, {})

    refreshed = await manager.refresh("demo")

    assert refreshed.access_token == "access_2"
    assert refreshed.refresh_token == "refresh_1"  # preserved
    assert manager.session("demo").refresh_count == 1


@pytest.mark.asyncio
async def test_refreshing_a_static_credential_is_refused(
    manager: MCPAuthManager,
) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    with pytest.raises(MCPAuthError, match="not refreshable"):
        await manager.refresh("demo")


@pytest.mark.asyncio
async def test_refreshing_an_unknown_provider_is_refused(
    manager: MCPAuthManager,
) -> None:
    with pytest.raises(MCPAuthError, match="No credential is stored"):
        await manager.refresh("nope")


@pytest.mark.asyncio
async def test_a_failed_refresh_marks_the_session_and_keeps_the_old_credential(
    store: CredentialStore, permissions: PermissionModel, bus: EventBus
) -> None:
    strategies = build_default_strategy_registry()
    strategies.register(_RefreshableStrategy(fail_refresh=True))
    manager = MCPAuthManager(store, strategies, permissions, event_bus=bus)
    await manager.authenticate("demo", AuthMethod.OAUTH2, {})

    with pytest.raises(MCPAuthError, match="refresh rejected"):
        await manager.refresh("demo")

    assert manager.session("demo").state is SessionState.FAILED
    # The frozen model means the old credential survived intact.
    credential = store.get("demo")
    assert credential is not None
    assert credential.access_token == "access_1"


# --- Revoke / forget ------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_clears_tokens_and_invalidates(manager: MCPAuthManager) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert await manager.revoke("demo") is True

    assert manager.validate("demo") is False
    assert manager.session("demo").state is SessionState.REVOKED


@pytest.mark.asyncio
async def test_revoke_keeps_the_record_for_auditability(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})
    await manager.revoke("demo")

    credential = store.get("demo")
    assert credential is not None
    assert credential.revoked is True
    assert credential.access_token == ""


@pytest.mark.asyncio
async def test_revoking_an_unknown_provider_returns_false(
    manager: MCPAuthManager,
) -> None:
    assert await manager.revoke("nope") is False


@pytest.mark.asyncio
async def test_forget_removes_the_record_entirely(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert manager.forget("demo") is True
    assert store.get("demo") is None


# --- Expiry / reconnect ---------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_credential_fails_validation(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    store.put(
        Credential(
            provider_id="demo",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=_NOW - timedelta(seconds=1),
        )
    )

    assert manager.validate("demo", now=_NOW) is False
    assert manager.session("demo").state is SessionState.EXPIRED


@pytest.mark.asyncio
async def test_expire_announces_once_not_repeatedly(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    store.put(
        Credential(
            provider_id="demo",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=_NOW - timedelta(seconds=1),
        )
    )

    assert await manager.expire("demo", now=_NOW) is True
    assert await manager.expire("demo", now=_NOW) is False  # already announced


@pytest.mark.asyncio
async def test_reconnect_refreshes_an_expired_refreshable_credential(
    store: CredentialStore, permissions: PermissionModel, bus: EventBus
) -> None:
    strategies = build_default_strategy_registry()
    strategies.register(_RefreshableStrategy())
    manager = MCPAuthManager(store, strategies, permissions, event_bus=bus)
    await manager.authenticate(
        "demo", AuthMethod.OAUTH2, {"expires_at": _NOW - timedelta(seconds=1)}
    )

    assert await manager.reconnect("demo") is True
    credential = store.get("demo")
    assert credential is not None
    assert credential.access_token == "access_2"


@pytest.mark.asyncio
async def test_reconnect_on_a_valid_credential_is_a_no_op_success(
    manager: MCPAuthManager,
) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert await manager.reconnect("demo") is True


@pytest.mark.asyncio
async def test_reconnect_reports_failure_for_an_expired_static_credential(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    """A static token that expired needs a human -- saying so beats a
    silent false with no explanation."""
    store.put(
        Credential(
            provider_id="demo",
            method=AuthMethod.API_KEY,
            access_token=_TOKEN,
            expires_at=_NOW - timedelta(days=1),
        )
    )

    assert await manager.reconnect("demo") is False
    assert "re-authentication is required" in manager.session("demo").error


@pytest.mark.asyncio
async def test_reconnect_refuses_a_revoked_credential(manager: MCPAuthManager) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})
    await manager.revoke("demo")

    assert await manager.reconnect("demo") is False


# --- Permission bridge ----------------------------------------------------------


@pytest.mark.asyncio
async def test_both_gates_must_pass(manager: MCPAuthManager, permissions: PermissionModel) -> None:
    await manager.authenticate(
        "demo", AuthMethod.API_KEY, {"token": _TOKEN, "scopes": ["repo:read"]}
    )

    # Gate 1: JARVIS permission not granted.
    allowed, reason = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("repo:read",)
    )
    assert allowed is False
    assert "JARVIS permission" in reason

    await permissions.grant(principal_for("demo"), "network")

    # Gate 2: the token does not carry the provider-side scope.
    allowed, reason = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("repo:write",)
    )
    assert allowed is False
    assert "provider scope" in reason

    # Both satisfied.
    allowed, reason = manager.authorize_capability(
        "demo", required_permissions=("network",), required_scopes=("repo:read",)
    )
    assert allowed is True
    assert reason == ""


@pytest.mark.asyncio
async def test_authorization_requires_authentication_first(
    manager: MCPAuthManager,
) -> None:
    allowed, reason = manager.authorize_capability("ghost")
    assert allowed is False
    assert "not authenticated" in reason


@pytest.mark.asyncio
async def test_the_two_scope_vocabularies_stay_distinct(
    manager: MCPAuthManager, permissions: PermissionModel
) -> None:
    """A JARVIS grant cannot conjure a provider-side scope, and vice
    versa -- that separation is the point of the bridge."""
    await manager.authenticate(
        "demo", AuthMethod.API_KEY, {"token": _TOKEN, "scopes": ["repo:read"]}
    )
    await permissions.grant(principal_for("demo"), "network")

    assert manager.jarvis_scopes_granted("demo", ("network",)) == {"network"}
    assert manager.provider_scopes("demo") == frozenset({"repo:read"})
    assert manager.jarvis_scopes_granted("demo", ("repo:read",)) == set()


# --- Health ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_health_classifies_every_credential(
    manager: MCPAuthManager, store: CredentialStore
) -> None:
    await manager.authenticate("good", AuthMethod.API_KEY, {"token": _TOKEN})
    store.put(
        Credential(
            provider_id="stale",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=_NOW - timedelta(seconds=1),
        )
    )
    store.put(
        Credential(
            provider_id="soon",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=_NOW + timedelta(seconds=30),
        )
    )

    health = await manager.collect_health(now=_NOW)

    assert health["count"] == 3
    assert "good" in health["authenticated"]
    assert health["expired"] == ["stale"]
    assert health["expiring_soon"] == ["soon"]
    assert health["can_persist"] is True


@pytest.mark.asyncio
async def test_health_sweep_announces_newly_expired_credentials(
    manager: MCPAuthManager, store: CredentialStore, bus: EventBus
) -> None:
    """Expiry detection rides the health poll rather than a second
    timer."""
    seen: list[MCPAuthStateChangedEvent] = []
    bus.subscribe(MCPAuthStateChangedEvent, seen.append)
    store.put(
        Credential(
            provider_id="stale",
            method=AuthMethod.BEARER_TOKEN,
            access_token=_TOKEN,
            expires_at=_NOW - timedelta(seconds=1),
        )
    )

    await manager.collect_health(now=_NOW)

    assert any(e.action == "token_expired" for e in seen)


@pytest.mark.asyncio
async def test_status_never_contains_a_token(manager: MCPAuthManager) -> None:
    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert _TOKEN not in str(manager.status("demo"))
    assert _TOKEN not in str(manager.public_snapshot())


# --- Events ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_full_lifecycle_publishes_its_actions(
    manager: MCPAuthManager, bus: EventBus
) -> None:
    seen: list[MCPAuthStateChangedEvent] = []
    bus.subscribe(MCPAuthStateChangedEvent, seen.append)

    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})
    await manager.revoke("demo")

    assert [e.action for e in seen] == [
        "authentication_started",
        "authentication_completed",
        "provider_authenticated",
        "credential_revoked",
        "provider_disconnected",
    ]
    assert all(a in AUTH_ACTIONS for a in (e.action for e in seen))


@pytest.mark.asyncio
async def test_events_never_carry_a_token(manager: MCPAuthManager, bus: EventBus) -> None:
    """Every WebSocket subscriber would otherwise receive it."""
    seen: list[MCPAuthStateChangedEvent] = []
    bus.subscribe(MCPAuthStateChangedEvent, seen.append)

    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert all(_TOKEN not in str(e) for e in seen)


@pytest.mark.asyncio
async def test_failure_publishes_authentication_failed(
    manager: MCPAuthManager, bus: EventBus
) -> None:
    seen: list[MCPAuthStateChangedEvent] = []
    bus.subscribe(MCPAuthStateChangedEvent, seen.append)

    with pytest.raises(MCPAuthError):
        await manager.authenticate("demo", AuthMethod.API_KEY, {})

    failed = next(e for e in seen if e.action == "authentication_failed")
    assert "requires a 'token'" in failed.detail


@pytest.mark.asyncio
async def test_manager_works_without_an_event_bus(
    store: CredentialStore, strategies: AuthStrategyRegistry, permissions: PermissionModel
) -> None:
    manager = MCPAuthManager(store, strategies, permissions, event_bus=None)

    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})
    assert manager.validate("demo") is True


# --- Session --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_is_created_on_demand_and_reused(
    manager: MCPAuthManager,
) -> None:
    session = manager.session("demo")
    assert session is manager.session("demo")
    assert session.state is SessionState.UNAUTHENTICATED


@pytest.mark.asyncio
async def test_session_counters_track_refreshes_and_failures(
    store: CredentialStore, permissions: PermissionModel, bus: EventBus
) -> None:
    strategies = build_default_strategy_registry()
    strategies.register(_RefreshableStrategy())
    manager = MCPAuthManager(store, strategies, permissions, event_bus=bus)
    await manager.authenticate("demo", AuthMethod.OAUTH2, {})
    await manager.refresh("demo")
    await manager.refresh("demo")

    session = manager.session("demo")
    assert session.refresh_count == 2
    assert session.failure_count == 0
    assert session.as_dict()["refresh_count"] == 2


@pytest.mark.asyncio
async def test_no_key_store_keeps_the_credential_in_memory_with_a_reason(
    tmp_path: Path, strategies: AuthStrategyRegistry, permissions: PermissionModel
) -> None:
    """An unconfigured install still authenticates for this session; the
    session records why it will not survive a restart."""
    keyless = CredentialStore(tmp_path / "creds.json", secret_key="")
    manager = MCPAuthManager(keyless, strategies, permissions)

    await manager.authenticate("demo", AuthMethod.API_KEY, {"token": _TOKEN})

    assert manager.validate("demo") is True
    # A caveat, not a failure -- so it lives on ``warning`` and
    # survives the successful transition that clears ``error``.
    assert "in memory only" in manager.session("demo").warning
    assert manager.session("demo").error == ""
    assert not (tmp_path / "creds.json").exists()
