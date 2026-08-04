"""Provider authentication sessions -- Milestone 10.5 Task Group D,
deliverable 5.

**Not a second session manager.** M9's
:class:`~jarvis.core.lifecycle.session_manager.SessionManager` owns
*user* sessions -- the Bearer tokens the REST API authenticates
callers with. This owns *provider* sessions: how long JARVIS's own
credential for an outbound integration stays usable. They share a word
and nothing else -- different subjects, different lifetimes, different
storage -- so merging them would couple an operator's login to a
provider's token expiry.

A session is derived state: it holds no secret of its own, only the
provider id, the runtime status, and counters. The credential lives in
the encrypted store; the session says whether it is currently working.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jarvis.core.mcp.auth.credentials import Credential, CredentialStatus


class SessionState(enum.StrEnum):
    #: No credential has been established yet.
    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATING = "authenticating"
    ACTIVE = "active"
    #: Credential present but past (or at) its expiry -- recoverable by
    #: refresh, unlike REVOKED.
    EXPIRED = "expired"
    REVOKED = "revoked"
    FAILED = "failed"


@dataclass(slots=True)
class ProviderSession:
    """One provider's live authentication state.

    Mutable in place, matching ``MCPConnection`` (Task Group A) and
    ``ProviderRecord`` (Task Group C) -- transitions are recorded on the
    record rather than by rebuilding a frozen one on every tick.
    """

    provider_id: str
    state: SessionState = SessionState.UNAUTHENTICATED
    #: Why the session failed. Cleared on every successful transition.
    error: str = ""
    #: A non-fatal caveat about an otherwise-successful session -- the
    #: credential being held in memory only, say. Kept separate from
    #: ``error`` because a successful transition clears the failure but
    #: must *not* erase a caveat that still applies.
    warning: str = ""
    #: Whether this session's expiry has already been announced, so the
    #: health sweep publishes ``token_expired`` once rather than on every
    #: poll. Derived state cannot answer this: a lazily-created session
    #: syncs straight to EXPIRED before anything has been announced.
    expiry_announced: bool = False
    authenticated_at: datetime | None = None
    last_refreshed_at: datetime | None = None
    refresh_count: int = 0
    failure_count: int = 0
    #: Provider-side scopes the credential actually carries -- distinct
    #: from the JARVIS permission scopes ``PermissionModel`` governs.
    granted_scopes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_active(self) -> bool:
        return self.state is SessionState.ACTIVE

    @property
    def needs_refresh(self) -> bool:
        return self.state is SessionState.EXPIRED

    def mark_authenticating(self) -> None:
        self.state = SessionState.AUTHENTICATING
        self.error = ""

    def mark_active(self, credential: Credential, *, now: datetime | None = None) -> None:
        moment = now or datetime.now(UTC)
        self.state = SessionState.ACTIVE
        self.error = ""
        self.expiry_announced = False
        self.granted_scopes = credential.scopes
        if self.authenticated_at is None:
            self.authenticated_at = moment

    def mark_refreshed(self, credential: Credential, *, now: datetime | None = None) -> None:
        self.mark_active(credential, now=now)
        self.last_refreshed_at = now or datetime.now(UTC)
        self.refresh_count += 1

    def mark_expired(self) -> None:
        self.state = SessionState.EXPIRED

    def mark_revoked(self) -> None:
        self.state = SessionState.REVOKED
        self.granted_scopes = ()

    def mark_failed(self, reason: str) -> None:
        self.state = SessionState.FAILED
        self.error = reason
        self.failure_count += 1

    def sync_from(self, credential: Credential | None, *, now: datetime | None = None) -> None:
        """Reconcile session state with what the credential actually
        says, so a token that expired while idle is reported honestly
        without anything having to poll it."""
        if credential is None:
            self.state = SessionState.UNAUTHENTICATED
            self.granted_scopes = ()
            return

        status = credential.status(now=now)
        if status is CredentialStatus.REVOKED:
            self.mark_revoked()
        elif status is CredentialStatus.EXPIRED:
            self.mark_expired()
        elif status is CredentialStatus.MISSING:
            self.state = SessionState.UNAUTHENTICATED
            self.granted_scopes = ()
        elif self.state not in (SessionState.FAILED, SessionState.AUTHENTICATING):
            self.state = SessionState.ACTIVE
            self.granted_scopes = credential.scopes

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "state": self.state.value,
            "error": self.error,
            "warning": self.warning,
            "authenticated_at": (
                self.authenticated_at.isoformat() if self.authenticated_at else None
            ),
            "last_refreshed_at": (
                self.last_refreshed_at.isoformat() if self.last_refreshed_at else None
            ),
            "refresh_count": self.refresh_count,
            "failure_count": self.failure_count,
            "granted_scopes": list(self.granted_scopes),
        }
