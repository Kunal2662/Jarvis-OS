"""Credential model and authentication vocabulary -- Milestone 10.5
Task Group D, deliverables 1 and 2.

**Secrets never reach a log line or a REST body from here.**
:class:`Credential` overrides ``__repr__``/``__str__`` to redact its
token fields, so a stray ``logger.info("... {}", credential)`` or an
exception rendering its arguments cannot leak one. Two serializers make
the distinction explicit and hard to get wrong by accident:

- :meth:`Credential.to_storage_dict` -- everything, for the encrypted
  store and nothing else.
- :meth:`Credential.to_public_dict` -- metadata only, for REST, logs
  and events. Reports *whether* a token exists and when it expires,
  never its value.

A dataclass with a redacting ``__repr__`` is deliberate rather than
``SecretStr`` everywhere: the tokens need arithmetic (expiry), rotation
metadata, and a storage round trip, and wrapping each field in
``SecretStr`` would push ``.get_secret_value()`` calls into every
consumer -- more places to leak from, not fewer.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

from jarvis.core.interfaces.mcp import MCPError


class MCPAuthError(MCPError):
    """An invalid credential, or an illegal authentication move."""


class AuthMethod(enum.StrEnum):
    """How a provider proves who it is.

    The vocabulary is fixed here so a future provider declares a known
    method rather than inventing a near-miss spelling, exactly as
    ``TRANSPORT_TYPES`` fixes the transport vocabulary. Adding a method
    later means adding a member plus a strategy -- no consumer changes.
    """

    API_KEY = "api_key"
    BEARER_TOKEN = "bearer_token"
    PERSONAL_ACCESS_TOKEN = "personal_access_token"
    OAUTH2 = "oauth2"
    CLIENT_CREDENTIALS = "client_credentials"
    #: No credential required. A real state, not a placeholder -- plenty
    #: of local MCP peers (a stdio subprocess on the same machine) need
    #: no authentication at all, and modelling that honestly avoids a
    #: fake empty credential standing in for "none needed".
    NONE = "none"


#: Methods that carry a token which can expire and be refreshed.
REFRESHABLE_METHODS: frozenset[AuthMethod] = frozenset(
    {AuthMethod.OAUTH2, AuthMethod.CLIENT_CREDENTIALS}
)

#: Methods satisfied by a single long-lived secret with no flow.
STATIC_METHODS: frozenset[AuthMethod] = frozenset(
    {AuthMethod.API_KEY, AuthMethod.BEARER_TOKEN, AuthMethod.PERSONAL_ACCESS_TOKEN}
)

#: How close to expiry a credential is reported as "expiring soon", so
#: a health surface can warn before anything actually breaks.
DEFAULT_EXPIRY_WARNING_SECONDS = 300.0

_REDACTED = "***redacted***"


class CredentialStatus(enum.StrEnum):
    ACTIVE = "active"
    EXPIRING = "expiring"
    EXPIRED = "expired"
    REVOKED = "revoked"
    MISSING = "missing"


@dataclass(frozen=True, slots=True)
class EncryptionMetadata:
    """How a stored credential was encrypted.

    Recorded per credential rather than globally so a key rotation can
    re-encrypt incrementally and still read anything not yet migrated
    -- ``key_id`` is what makes that possible. ``algorithm`` is stored
    for the same reason: a future change of cipher must be able to read
    what the previous one wrote.
    """

    algorithm: str = "fernet"
    key_id: str = "default"
    encrypted_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "encrypted_at": self.encrypted_at.isoformat() if self.encrypted_at else None,
        }


@dataclass(frozen=True, slots=True)
class Credential:
    """One provider's authentication material.

    Frozen: a refresh produces a *new* credential
    (:meth:`with_refreshed`) rather than mutating the old one in place,
    so a failed refresh can never leave a half-updated credential behind.
    """

    provider_id: str
    method: AuthMethod = AuthMethod.NONE
    access_token: str = ""
    refresh_token: str = ""
    expires_at: datetime | None = None
    scopes: tuple[str, ...] = ()
    account_id: str = ""
    encryption: EncryptionMetadata = field(default_factory=EncryptionMetadata)
    revoked: bool = False

    # ------------------------------------------------------------------
    # Redaction -- the reason this class is not a plain dataclass
    # ------------------------------------------------------------------
    def __repr__(self) -> str:
        return (
            f"Credential(provider_id={self.provider_id!r}, method={self.method.value!r}, "
            f"access_token={_REDACTED if self.access_token else ''!r}, "
            f"refresh_token={_REDACTED if self.refresh_token else ''!r}, "
            f"expires_at={self.expires_at!r}, scopes={self.scopes!r}, "
            f"account_id={self.account_id!r}, revoked={self.revoked!r})"
        )

    __str__ = __repr__

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def has_access_token(self) -> bool:
        return bool(self.access_token)

    @property
    def has_refresh_token(self) -> bool:
        return bool(self.refresh_token)

    @property
    def is_refreshable(self) -> bool:
        return self.method in REFRESHABLE_METHODS and self.has_refresh_token

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return _aware(self.expires_at) <= _aware(now or datetime.now(UTC))

    def expires_within(self, seconds: float, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        moment = _aware(now or datetime.now(UTC))
        return _aware(self.expires_at) <= moment + timedelta(seconds=seconds)

    def seconds_until_expiry(self, *, now: datetime | None = None) -> float | None:
        if self.expires_at is None:
            return None
        delta = _aware(self.expires_at) - _aware(now or datetime.now(UTC))
        return delta.total_seconds()

    def status(
        self,
        *,
        now: datetime | None = None,
        warning_seconds: float = DEFAULT_EXPIRY_WARNING_SECONDS,
    ) -> CredentialStatus:
        if self.revoked:
            return CredentialStatus.REVOKED
        if self.method is not AuthMethod.NONE and not self.has_access_token:
            return CredentialStatus.MISSING
        if self.is_expired(now=now):
            return CredentialStatus.EXPIRED
        if self.expires_within(warning_seconds, now=now):
            return CredentialStatus.EXPIRING
        return CredentialStatus.ACTIVE

    def is_valid(self, *, now: datetime | None = None) -> bool:
        return self.status(now=now) in (CredentialStatus.ACTIVE, CredentialStatus.EXPIRING)

    # ------------------------------------------------------------------
    # Transitions (all produce a new credential)
    # ------------------------------------------------------------------
    def with_refreshed(
        self,
        access_token: str,
        *,
        refresh_token: str | None = None,
        expires_at: datetime | None = None,
        scopes: tuple[str, ...] | None = None,
    ) -> Credential:
        """A provider that does not return a new refresh token keeps the
        existing one -- dropping it would silently make the credential
        unrefreshable next time."""
        return replace(
            self,
            access_token=access_token,
            refresh_token=self.refresh_token if refresh_token is None else refresh_token,
            expires_at=expires_at,
            scopes=self.scopes if scopes is None else scopes,
            revoked=False,
        )

    def revoke(self) -> Credential:
        """Clears both tokens as well as flagging revocation -- a
        revoked credential that still holds its secret is a credential
        waiting to leak."""
        return replace(self, access_token="", refresh_token="", revoked=True)

    def with_encryption(self, encryption: EncryptionMetadata) -> Credential:
        return replace(self, encryption=encryption)

    # ------------------------------------------------------------------
    # Serialization -- two forms, deliberately
    # ------------------------------------------------------------------
    def to_storage_dict(self) -> dict[str, Any]:
        """Full material. Only the encrypted store may call this."""
        return {
            "provider_id": self.provider_id,
            "method": self.method.value,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "scopes": list(self.scopes),
            "account_id": self.account_id,
            "encryption": self.encryption.as_dict(),
            "revoked": self.revoked,
        }

    def to_public_dict(
        self,
        *,
        now: datetime | None = None,
        warning_seconds: float = DEFAULT_EXPIRY_WARNING_SECONDS,
    ) -> dict[str, Any]:
        """Metadata only -- safe for REST, logs and events. Reports
        whether a token exists, never what it is."""
        return {
            "provider_id": self.provider_id,
            "method": self.method.value,
            "status": self.status(now=now, warning_seconds=warning_seconds).value,
            "has_access_token": self.has_access_token,
            "has_refresh_token": self.has_refresh_token,
            "is_refreshable": self.is_refreshable,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "seconds_until_expiry": self.seconds_until_expiry(now=now),
            "scopes": list(self.scopes),
            "account_id": self.account_id,
            "revoked": self.revoked,
            "encryption": self.encryption.as_dict(),
        }

    @classmethod
    def from_storage_dict(cls, raw: dict[str, Any]) -> Credential:
        encryption = raw.get("encryption") or {}
        encrypted_at = encryption.get("encrypted_at")
        return cls(
            provider_id=str(raw.get("provider_id") or ""),
            method=AuthMethod(raw.get("method") or AuthMethod.NONE.value),
            access_token=str(raw.get("access_token") or ""),
            refresh_token=str(raw.get("refresh_token") or ""),
            expires_at=_parse_dt(raw.get("expires_at")),
            scopes=tuple(raw.get("scopes") or ()),
            account_id=str(raw.get("account_id") or ""),
            encryption=EncryptionMetadata(
                algorithm=str(encryption.get("algorithm") or "fernet"),
                key_id=str(encryption.get("key_id") or "default"),
                encrypted_at=_parse_dt(encrypted_at),
            ),
            revoked=bool(raw.get("revoked", False)),
        )


def _aware(value: datetime) -> datetime:
    """SQLite and JSON round-trips both hand back naive datetimes; every
    comparison here normalizes rather than assuming tz-awareness."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None
