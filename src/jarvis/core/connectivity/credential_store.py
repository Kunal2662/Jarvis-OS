"""Encrypted connector credential storage -- Milestone 12 Task Group B,
Phase 1.

Persists to ``<data_dir>/config/connectivity_credentials.json``, reusing
the existing storage convention ``PermissionModel``,
``CrashRecoveryManager``, ``ApiCenterService`` and MCP's own
``CredentialStore`` (``core/mcp/auth/store.py``) already share, and the
existing Fernet helpers in :mod:`jarvis.utils.crypto`. No second crypto
stack, no new dependency, no new location.

**A sibling of MCP's ``CredentialStore``, not a caller of it.** The two
solve the same technical problem (encrypt-at-rest, refuse-to-persist-
without-a-key, per-value encryption, rotation-ready) for two unrelated
domains -- MCP provider credentials and device-connector credentials.
Importing MCP's auth module from here would couple two subsystems that
have nothing to do with each other beyond sharing a technique; the
technique itself (Fernet via ``jarvis.utils.crypto``) is what's shared,
the same way two unrelated repositories both use SQLAlchemy sessions
without being "the same service." ``EncryptionMetadata`` is duplicated
here rather than imported for the same reason -- it is three fields and
importing it would be the only thing pulling ``core/mcp/auth`` into
``core/connectivity``.

**Refuses to persist without a real key**, the same hardening
``core/mcp/auth/store.py`` applies over the older ``ApiCenterService``
precedent: a device-connector credential (a Home Assistant long-lived
token, a future vendor OAuth token) is not the kind of secret worth
writing in plaintext as a fallback. In-memory operation still works, so
an unconfigured install can connect for the current session and simply
will not remember it.

**Nothing here logs a secret.** Log lines carry a connector type and an
outcome; :class:`ConnectorCredential` redacts its own ``repr`` the same
way MCP's ``Credential`` does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ConfigError
from jarvis.core.interfaces.connectivity import ConnectivityError
from jarvis.core.logging.logger import get_logger
from jarvis.utils.crypto import decrypt, encrypt

if TYPE_CHECKING:
    from pathlib import Path

_logger = get_logger("jarvis.core.connectivity.credential_store")

#: The placeholder shipped in ``.env.example``. Treated as "no key
#: configured" -- encrypting with a value every install shares would be
#: theatre, not encryption. Same constant MCP's own store checks.
_PLACEHOLDER_KEY = "CHANGE_ME_TO_A_FERNET_KEY"

_REDACTED = "***redacted***"


class CredentialEncryptionError(ConnectivityError):
    """Raised when persistence is attempted without a usable key."""


@dataclass(frozen=True, slots=True)
class EncryptionMetadata:
    """How a stored credential was encrypted. Recorded per credential
    so a key rotation can re-encrypt incrementally and still read
    anything not yet migrated."""

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
class ConnectorCredential:
    """One connector's authentication material.

    ``secrets`` is a flat string-to-string map rather than a single
    ``access_token`` field: a Home Assistant long-lived token is one
    secret, but an MQTT broker connection is a username *and* a
    password, and a future OAuth2 vendor connector needs an access
    token *and* a refresh token. One flexible map covers all three
    without forcing an OAuth-shaped field set onto a connector that has
    no OAuth flow at all.

    Frozen: rotating or updating a credential produces a *new* value
    (:meth:`with_secrets`) rather than mutating the old one in place.
    """

    connector_type: str
    secrets: dict[str, str] = field(default_factory=dict)
    account_id: str = ""
    expires_at: datetime | None = None
    encryption: EncryptionMetadata = field(default_factory=EncryptionMetadata)
    revoked: bool = False

    def __repr__(self) -> str:
        redacted = {key: _REDACTED for key in self.secrets} if self.secrets else {}
        return (
            f"ConnectorCredential(connector_type={self.connector_type!r}, "
            f"secrets={redacted!r}, account_id={self.account_id!r}, "
            f"expires_at={self.expires_at!r}, revoked={self.revoked!r})"
        )

    __str__ = __repr__

    @property
    def has_secrets(self) -> bool:
        return bool(self.secrets)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        return _aware(self.expires_at) <= _aware(now or datetime.now(UTC))

    def with_secrets(
        self, secrets: dict[str, str], *, expires_at: datetime | None = None
    ) -> ConnectorCredential:
        return replace(self, secrets=dict(secrets), expires_at=expires_at, revoked=False)

    def revoke(self) -> ConnectorCredential:
        """Clears the secrets as well as flagging revocation -- a
        revoked credential that still holds its secrets is a credential
        waiting to leak."""
        return replace(self, secrets={}, revoked=True)

    def with_encryption(self, encryption: EncryptionMetadata) -> ConnectorCredential:
        return replace(self, encryption=encryption)

    def to_storage_dict(self) -> dict[str, Any]:
        """Full material. Only the encrypted store may call this."""
        return {
            "connector_type": self.connector_type,
            "secrets": dict(self.secrets),
            "account_id": self.account_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "encryption": self.encryption.as_dict(),
            "revoked": self.revoked,
        }

    def to_public_dict(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Metadata only -- safe for REST, logs and events. Reports
        which secret keys exist, never their values."""
        return {
            "connector_type": self.connector_type,
            "secret_keys": sorted(self.secrets),
            "has_secrets": self.has_secrets,
            "account_id": self.account_id,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": self.is_expired(now=now),
            "revoked": self.revoked,
            "encryption": self.encryption.as_dict(),
        }

    @classmethod
    def from_storage_dict(cls, raw: dict[str, Any]) -> ConnectorCredential:
        encryption = raw.get("encryption") or {}
        return cls(
            connector_type=str(raw.get("connector_type") or ""),
            secrets=dict(raw.get("secrets") or {}),
            account_id=str(raw.get("account_id") or ""),
            expires_at=_parse_dt(raw.get("expires_at")),
            encryption=EncryptionMetadata(
                algorithm=str(encryption.get("algorithm") or "fernet"),
                key_id=str(encryption.get("key_id") or "default"),
                encrypted_at=_parse_dt(encryption.get("encrypted_at")),
            ),
            revoked=bool(raw.get("revoked", False)),
        )


class ConnectorCredentialStore:
    """Encrypted-at-rest credential persistence, keyed by connector
    type. Structurally mirrors ``core/mcp/auth/store.py``'s
    ``CredentialStore`` -- see this module's own docstring for why it
    is a sibling rather than a shared instance."""

    def __init__(
        self,
        store_path: Path,
        *,
        secret_key: str = "",
        key_id: str = "default",
    ) -> None:
        self._store_path = store_path
        self._secret_key = secret_key if secret_key != _PLACEHOLDER_KEY else ""
        self._key_id = key_id
        self._credentials: dict[str, ConnectorCredential] = {}
        self._loaded = False

    @property
    def can_persist(self) -> bool:
        return bool(self._secret_key)

    def _require_key(self) -> str:
        if not self._secret_key:
            raise CredentialEncryptionError(
                "Refusing to persist connectivity credentials: no encryption key is "
                "configured. Set JARVIS_SECURITY_SECRET_KEY to a valid Fernet key. "
                "Credentials remain usable in memory for this session."
            )
        return self._secret_key

    def get(self, connector_type: str) -> ConnectorCredential | None:
        self._ensure_loaded()
        return self._credentials.get(connector_type)

    def has(self, connector_type: str) -> bool:
        self._ensure_loaded()
        return connector_type in self._credentials

    @property
    def connector_types(self) -> tuple[str, ...]:
        self._ensure_loaded()
        return tuple(self._credentials)

    def put(self, credential: ConnectorCredential, *, persist: bool = True) -> ConnectorCredential:
        """*persist=False* keeps it in memory only -- the escape hatch
        an unconfigured install uses, chosen explicitly by the caller
        rather than silently degraded to by the store."""
        self._ensure_loaded()
        stamped = credential.with_encryption(
            EncryptionMetadata(
                algorithm="fernet",
                key_id=self._key_id,
                encrypted_at=datetime.now(UTC) if persist and self.can_persist else None,
            )
        )
        self._credentials[credential.connector_type] = stamped
        if persist:
            self._save()
        return stamped

    def delete(self, connector_type: str, *, persist: bool = True) -> bool:
        self._ensure_loaded()
        removed = self._credentials.pop(connector_type, None) is not None
        if removed and persist and self.can_persist:
            self._save()
        return removed

    def public_snapshot(self, *, now: datetime | None = None) -> tuple[dict[str, Any], ...]:
        """Metadata for every credential -- never a secret value."""
        self._ensure_loaded()
        return tuple(c.to_public_dict(now=now) for c in self._credentials.values())

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _logger.warning(
                "Could not read connectivity credential store {}: {}", self._store_path, err
            )
            return

        for row in raw.get("credentials") or []:
            try:
                self._credentials[row["connector_type"]] = self._row_to_credential(row)
            except (KeyError, ValueError, ConfigError) as err:
                # One unreadable record must not make every other
                # credential unavailable -- the same fault isolation
                # MCP's own credential store applies.
                _logger.warning(
                    "Skipping unreadable connectivity credential for {!r}: {}",
                    row.get("connector_type", "<unknown>"),
                    err,
                )

    def _save(self) -> None:
        key = self._require_key()
        payload = {
            "version": 1,
            "key_id": self._key_id,
            "credentials": [self._credential_to_row(c, key) for c in self._credentials.values()],
        }
        try:
            self._store_path.parent.mkdir(parents=True, exist_ok=True)
            self._store_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as err:
            raise CredentialEncryptionError(
                f"Could not write connectivity credential store {self._store_path}: {err}"
            ) from err

    def _credential_to_row(self, credential: ConnectorCredential, key: str) -> dict[str, Any]:
        row = credential.to_storage_dict()
        row["secrets"] = {
            name: encrypt(key, value) if value else "" for name, value in row["secrets"].items()
        }
        return row

    def _row_to_credential(self, row: dict[str, Any]) -> ConnectorCredential:
        decoded = dict(row)
        raw_secrets = dict(decoded.get("secrets") or {})
        if self._secret_key:
            decoded["secrets"] = {
                name: decrypt(self._secret_key, value) if value else ""
                for name, value in raw_secrets.items()
            }
        else:
            # No key: the metadata is still useful for diagnostics, but
            # the secrets are not recoverable -- report that honestly
            # rather than handing back ciphertext that looks like one.
            decoded["secrets"] = dict.fromkeys(raw_secrets, "")
        return ConnectorCredential.from_storage_dict(decoded)


def _aware(value: datetime) -> datetime:
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
