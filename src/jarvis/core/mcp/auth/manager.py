"""Authentication Manager -- Milestone 10.5 Task Group D, deliverables
4, 6, 7 and 8.

Owns the credential lifecycle (authenticate / refresh / revoke /
validate / expire / reconnect), the per-provider session, the bridge to
M9's ``PermissionModel``, and the health payload M9's ``HealthMonitor``
collects.

**Three things it deliberately is not:**

- *Not a permission system.* :meth:`authorize_capability` reads the
  existing ``PermissionModel`` (namespaced ``mcp:<provider_id>``, the
  prefix Task Group A established) and the credential's own
  provider-side scopes. It stores no grants and defines no scope
  vocabulary of its own.
- *Not a session manager.* M9's ``SessionManager`` owns *user* sessions
  (the Bearer tokens the REST API authenticates callers with). This
  owns *provider* sessions -- how long JARVIS's credential for an
  outbound integration stays usable. Different subject, different
  lifetime, no shared state.
- *Not a health subsystem.* :meth:`collect_health` returns a plain dict
  for ``HealthMonitor.register_collector``, the same extension point
  Task Groups A, B and C already ride.

**The permission bridge, precisely.** Two independent gates guard a
capability, and conflating them would be a security bug:

1. *JARVIS-side* -- has the operator granted this provider the
   ``PERMISSION_SCOPES`` entry the capability requires? That is
   ``PermissionModel``'s decision, and it is about what JARVIS is
   allowed to do on the user's behalf.
2. *Provider-side* -- does the credential actually carry the scope the
   remote service demands (``repo:read``, say)? That is the token's
   business, and no amount of local granting can conjure it.

A capability is usable only when **both** pass.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.events.events import MCPAuthStateChangedEvent
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.auth.credentials import (
    DEFAULT_EXPIRY_WARNING_SECONDS,
    AuthMethod,
    Credential,
    CredentialStatus,
    MCPAuthError,
)
from jarvis.core.mcp.auth.session import ProviderSession
from jarvis.core.mcp.auth.store import CredentialEncryptionError
from jarvis.core.mcp.server import principal_for

if TYPE_CHECKING:
    from collections.abc import Collection

    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.mcp.auth.store import CredentialStore
    from jarvis.core.mcp.auth.strategies import AuthStrategyRegistry
    from jarvis.core.plugins.permissions import PermissionModel

_logger = get_logger("jarvis.core.mcp.auth.manager")

#: Lifecycle transitions published on the relay, matching this task
#: group's own deliverable list.
AUTH_ACTIONS: frozenset[str] = frozenset(
    {
        "authentication_started",
        "authentication_completed",
        "authentication_failed",
        "token_refreshed",
        "token_expired",
        "credential_revoked",
        "provider_authenticated",
        "provider_disconnected",
    }
)


class MCPAuthManager:
    """Credential lifecycle, provider sessions, and the permission bridge."""

    def __init__(
        self,
        store: CredentialStore,
        strategies: AuthStrategyRegistry,
        permission_model: PermissionModel,
        *,
        event_bus: EventBus | None = None,
        expiry_warning_seconds: float = DEFAULT_EXPIRY_WARNING_SECONDS,
    ) -> None:
        self._store = store
        self._strategies = strategies
        self._permissions = permission_model
        self._event_bus = event_bus
        self._warning_seconds = expiry_warning_seconds
        self._sessions: dict[str, ProviderSession] = {}

    # ------------------------------------------------------------------
    # Sessions
    # ------------------------------------------------------------------
    def session(self, provider_id: str) -> ProviderSession:
        """The provider's session, created on first reference. Sessions
        are derived state -- creating one costs nothing and holds no
        secret."""
        session = self._sessions.get(provider_id)
        if session is None:
            session = ProviderSession(provider_id=provider_id)
            session.sync_from(self._store.get(provider_id))
            self._sessions[provider_id] = session
        return session

    @property
    def provider_ids(self) -> tuple[str, ...]:
        """Every provider with a credential or a session -- the union,
        so a provider that failed before storing anything is still
        visible."""
        return tuple(sorted(set(self._store.provider_ids) | set(self._sessions)))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def authenticate(
        self,
        provider_id: str,
        method: AuthMethod,
        request: dict[str, Any] | None = None,
        *,
        persist: bool = True,
    ) -> Credential:
        """Obtain and store a credential.

        *request* carries the method's own inputs (a ``token`` for the
        static methods). Its contents are never logged or published --
        only the outcome is.
        """
        session = self.session(provider_id)
        session.mark_authenticating()
        await self._publish(provider_id, "authentication_started", method=method)

        try:
            strategy = self._strategies.get(method)
            credential = await strategy.authenticate(provider_id, request or {})
        except Exception as err:
            session.mark_failed(str(err))
            await self._publish(
                provider_id, "authentication_failed", method=method, detail=str(err)
            )
            raise

        stored = self._store_credential(credential, persist=persist, session=session)
        session.mark_active(stored)
        await self._publish(provider_id, "authentication_completed", method=method)
        await self._publish(provider_id, "provider_authenticated", method=method)
        return stored

    async def refresh(self, provider_id: str, *, persist: bool = True) -> Credential:
        """Exchange a refresh token for a fresh credential.

        Refuses loudly rather than silently no-op'ing when the method
        cannot be refreshed -- a caller that believes it renewed a
        static API key would otherwise keep using an expired one.
        """
        credential = self._require_credential(provider_id)
        session = self.session(provider_id)

        if not credential.is_refreshable:
            raise MCPAuthError(
                f"Credential for {provider_id!r} is not refreshable "
                f"(method={credential.method.value}, has_refresh_token="
                f"{credential.has_refresh_token})."
            )

        try:
            strategy = self._strategies.get(credential.method)
            refreshed = await strategy.refresh(credential)
        except Exception as err:
            session.mark_failed(str(err))
            await self._publish(
                provider_id,
                "authentication_failed",
                method=credential.method,
                detail=f"refresh failed: {err}",
            )
            raise

        stored = self._store_credential(refreshed, persist=persist, session=session)
        session.mark_refreshed(stored)
        await self._publish(provider_id, "token_refreshed", method=stored.method)
        return stored

    async def revoke(self, provider_id: str, *, persist: bool = True) -> bool:
        """Invalidate the credential and clear its tokens.

        Returns whether anything was revoked. The credential record is
        kept (revoked, tokens cleared) rather than deleted, so the
        revocation itself stays auditable -- :meth:`forget` is the
        method that removes it entirely.
        """
        credential = self._store.get(provider_id)
        if credential is None:
            return False

        session = self.session(provider_id)
        try:
            strategy = self._strategies.get(credential.method)
            revoked = await strategy.revoke(credential)
        except Exception as err:
            # A remote revoke failing must not leave the local token
            # usable -- clear it locally regardless and report why.
            _logger.warning("Remote revoke for {!r} failed: {}", provider_id, err)
            revoked = credential.revoke()

        self._store_credential(revoked, persist=persist, session=session)
        session.mark_revoked()
        await self._publish(provider_id, "credential_revoked", method=credential.method)
        await self._publish(provider_id, "provider_disconnected", method=credential.method)
        return True

    def forget(self, provider_id: str, *, persist: bool = True) -> bool:
        """Delete the credential and its session outright."""
        removed = self._store.delete(provider_id, persist=persist)
        self._sessions.pop(provider_id, None)
        return removed

    def validate(self, provider_id: str, *, now: datetime | None = None) -> bool:
        """Cheap local check -- never a network call. Also reconciles the
        session, so a token that expired while idle is reported honestly
        without anything having to poll it."""
        credential = self._store.get(provider_id)
        session = self.session(provider_id)
        session.sync_from(credential, now=now)
        if credential is None:
            return False
        strategy = (
            self._strategies.get(credential.method)
            if self._strategies.supports(credential.method)
            else None
        )
        return strategy.validate(credential) if strategy else credential.is_valid(now=now)

    async def expire(self, provider_id: str, *, now: datetime | None = None) -> bool:
        """Mark an expired credential as such and announce it.

        Called by the health sweep rather than a timer of its own --
        adding a second scheduler for something ``HealthMonitor``
        already polls would be the duplicate runtime this task group
        forbids.
        """
        credential = self._store.get(provider_id)
        if credential is None or not credential.is_expired(now=now):
            return False
        session = self.session(provider_id)
        if session.expiry_announced:
            return False
        session.mark_expired()
        session.expiry_announced = True
        await self._publish(provider_id, "token_expired", method=credential.method)
        return True

    async def reconnect(self, provider_id: str, *, persist: bool = True) -> bool:
        """Restore a usable credential without re-prompting the user.

        Refreshes when the method supports it; otherwise reports failure
        rather than pretending -- a static token that has expired needs
        a human to supply a new one, and saying so is more useful than
        a silent false.
        """
        credential = self._store.get(provider_id)
        if credential is None:
            return False
        if credential.revoked:
            return False
        if credential.is_valid():
            self.session(provider_id).sync_from(credential)
            return True

        if not credential.is_refreshable:
            self.session(provider_id).mark_failed(
                f"{credential.method.value} credentials cannot be refreshed; "
                "re-authentication is required."
            )
            return False

        try:
            await self.refresh(provider_id, persist=persist)
        except (MCPAuthError, CredentialEncryptionError) as err:
            _logger.warning("Reconnect for {!r} failed: {}", provider_id, err)
            return False
        return True

    # ------------------------------------------------------------------
    # Permission bridge (deliverable 6)
    # ------------------------------------------------------------------
    def jarvis_scopes_granted(self, provider_id: str, scopes: Collection[str]) -> set[str]:
        """Which of *scopes* the operator has granted this provider,
        via the existing ``PermissionModel``."""
        principal = principal_for(provider_id)
        return {scope for scope in scopes if self._permissions.is_granted(principal, scope)}

    def provider_scopes(self, provider_id: str) -> frozenset[str]:
        """The provider-side scopes the credential actually carries --
        distinct from JARVIS's own permission vocabulary."""
        credential = self._store.get(provider_id)
        return frozenset(credential.scopes) if credential else frozenset()

    def authorize_capability(
        self,
        provider_id: str,
        *,
        required_permissions: Collection[str] = (),
        required_scopes: Collection[str] = (),
    ) -> tuple[bool, str]:
        """Both gates, in one answer.

        Returns ``(allowed, reason)``. The reason names *which* gate
        refused, because "permission not granted" and "the token does
        not carry that scope" call for completely different fixes.
        """
        if not self.validate(provider_id):
            credential = self._store.get(provider_id)
            status = (
                credential.status(warning_seconds=self._warning_seconds).value
                if credential
                else CredentialStatus.MISSING.value
            )
            return False, f"Provider {provider_id!r} is not authenticated (status: {status})."

        missing_permissions = sorted(
            set(required_permissions)
            - self.jarvis_scopes_granted(provider_id, required_permissions)
        )
        if missing_permissions:
            return False, (
                f"JARVIS permission(s) not granted for {provider_id!r}: {missing_permissions}."
            )

        missing_scopes = sorted(set(required_scopes) - self.provider_scopes(provider_id))
        if missing_scopes:
            return False, (
                f"Credential for {provider_id!r} does not carry provider scope(s): "
                f"{missing_scopes}."
            )
        return True, ""

    # ------------------------------------------------------------------
    # Reporting / health (deliverable 8)
    # ------------------------------------------------------------------
    def status(self, provider_id: str, *, now: datetime | None = None) -> dict[str, Any]:
        """Metadata only -- never a token value."""
        credential = self._store.get(provider_id)
        session = self.session(provider_id)
        session.sync_from(credential, now=now)
        return {
            "provider_id": provider_id,
            "session": session.as_dict(),
            "credential": (
                credential.to_public_dict(now=now, warning_seconds=self._warning_seconds)
                if credential
                else None
            ),
            "authenticated": self.validate(provider_id, now=now),
            "persistable": self._store.can_persist,
        }

    def public_snapshot(self, *, now: datetime | None = None) -> tuple[dict[str, Any], ...]:
        return tuple(self.status(pid, now=now) for pid in self.provider_ids)

    async def sweep(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Announce every credential that has newly expired.

        Driven by the health poll rather than its own loop -- returns the
        provider ids that transitioned, so a caller can act on them.
        """
        expired: list[str] = []
        for provider_id in self.provider_ids:
            if await self.expire(provider_id, now=now):
                expired.append(provider_id)
        return tuple(expired)

    async def collect_health(self, *, now: datetime | None = None) -> dict[str, Any]:
        """The payload M9's ``HealthMonitor`` merges under its own key.

        Sweeping here is deliberate: the health poll is already the
        thing that runs periodically, so expiry detection rides it
        instead of adding a second timer.
        """
        await self.sweep(now=now)
        moment = now or datetime.now(UTC)

        providers: list[dict[str, Any]] = []
        expiring: list[str] = []
        expired: list[str] = []
        for provider_id in self.provider_ids:
            credential = self._store.get(provider_id)
            status = (
                credential.status(now=moment, warning_seconds=self._warning_seconds)
                if credential
                else CredentialStatus.MISSING
            )
            if status is CredentialStatus.EXPIRING:
                expiring.append(provider_id)
            elif status is CredentialStatus.EXPIRED:
                expired.append(provider_id)
            providers.append(
                {
                    "provider_id": provider_id,
                    "status": status.value,
                    "session_state": self.session(provider_id).state.value,
                    "seconds_until_expiry": (
                        credential.seconds_until_expiry(now=moment) if credential else None
                    ),
                }
            )

        return {
            "count": len(providers),
            "authenticated": [
                p["provider_id"]
                for p in providers
                if p["status"] in (CredentialStatus.ACTIVE.value, CredentialStatus.EXPIRING.value)
            ],
            "expiring_soon": expiring,
            "expired": expired,
            "can_persist": self._store.can_persist,
            "supported_methods": list(self._strategies.supported_methods),
            "providers": providers,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _require_credential(self, provider_id: str) -> Credential:
        credential = self._store.get(provider_id)
        if credential is None:
            raise MCPAuthError(f"No credential is stored for provider {provider_id!r}.")
        return credential

    def _store_credential(
        self, credential: Credential, *, persist: bool, session: ProviderSession
    ) -> Credential:
        """Persist when asked and possible; fall back to memory with a
        recorded reason rather than failing the authentication outright
        -- an unconfigured install can still work for this session."""
        if persist and not self._store.can_persist:
            session.warning = (
                "Credential held in memory only: no encryption key is configured, and "
                "writing a token in plaintext is not an acceptable fallback."
            )
            _logger.warning(
                "Not persisting credential for {!r}: no encryption key configured.",
                credential.provider_id,
            )
            return self._store.put(credential, persist=False)
        return self._store.put(credential, persist=persist)

    async def _publish(
        self,
        provider_id: str,
        action: str,
        *,
        method: AuthMethod = AuthMethod.NONE,
        detail: str = "",
    ) -> None:
        if self._event_bus is None:
            return
        await self._event_bus.publish(
            MCPAuthStateChangedEvent(
                provider_id=provider_id,
                action=action,
                method=method.value,
                session_state=self.session(provider_id).state.value,
                detail=detail,
            )
        )
