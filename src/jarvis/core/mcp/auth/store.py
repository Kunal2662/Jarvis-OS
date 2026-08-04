"""Encrypted credential storage -- Milestone 10.5 Task Group D,
deliverable 3.

Persists to ``<data_dir>/config/mcp_credentials.json``, reusing the
existing storage convention ``PermissionModel``, ``CrashRecoveryManager``
and ``ApiCenterService`` already share, and the existing Fernet helpers
in :mod:`jarvis.utils.crypto`. No second crypto stack, no new
dependency, no new location.

**One deliberate hardening over the ``ApiCenterService`` precedent.**
That service encrypts secret fields *when* a real key is configured and
writes plaintext when one is not -- a reasonable trade for API
definitions that are mostly non-secret metadata. Access and refresh
tokens are not that: writing one in plaintext is strictly worse than
not persisting it. So this store **refuses to persist** when no real
key is configured (:class:`CredentialEncryptionError`), and callers get
a loud failure instead of a quiet plaintext file. In-memory operation
still works, so an unconfigured install can authenticate for the
current session and simply will not remember it.

**Nothing here logs a token.** Log lines carry a provider id and an
outcome; :class:`~jarvis.core.mcp.auth.credentials.Credential` redacts
its own ``repr`` so even an accidental interpolation cannot leak one.

**Rotation-ready** by construction: each record stores the ``key_id``
that encrypted it (``EncryptionMetadata``), and :meth:`rotate` re-writes
every record under a new key. Nothing assumes one key forever.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ConfigError
from jarvis.core.logging.logger import get_logger
from jarvis.core.mcp.auth.credentials import (
    Credential,
    EncryptionMetadata,
    MCPAuthError,
)
from jarvis.utils.crypto import decrypt, encrypt

if TYPE_CHECKING:
    from pathlib import Path

_logger = get_logger("jarvis.core.mcp.auth.store")

#: The placeholder shipped in ``.env.example``. Treated as "no key
#: configured" -- encrypting with a value every install shares would be
#: theatre, not encryption.
_PLACEHOLDER_KEY = "CHANGE_ME_TO_A_FERNET_KEY"

#: Fields encrypted individually rather than encrypting the whole file:
#: the surrounding metadata (expiry, scopes, status) stays readable for
#: diagnostics without a key, while the secrets never are.
_SECRET_FIELDS = ("access_token", "refresh_token")


class CredentialEncryptionError(MCPAuthError):
    """Raised when persistence is attempted without a usable key."""


class CredentialStore:
    """Encrypted-at-rest credential persistence, keyed by provider id."""

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
        self._credentials: dict[str, Credential] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Key state
    # ------------------------------------------------------------------
    @property
    def can_persist(self) -> bool:
        """Whether a real encryption key is configured. Callers check
        this to explain *why* a credential will not survive a restart,
        rather than discovering it at write time."""
        return bool(self._secret_key)

    @property
    def key_id(self) -> str:
        return self._key_id

    def _require_key(self) -> str:
        if not self._secret_key:
            raise CredentialEncryptionError(
                "Refusing to persist MCP credentials: no encryption key is configured. "
                "Set JARVIS_SECURITY_SECRET_KEY to a valid Fernet key. Credentials "
                "remain usable in memory for this session."
            )
        return self._secret_key

    # ------------------------------------------------------------------
    # Read / write
    # ------------------------------------------------------------------
    def get(self, provider_id: str) -> Credential | None:
        self._ensure_loaded()
        return self._credentials.get(provider_id)

    def has(self, provider_id: str) -> bool:
        self._ensure_loaded()
        return provider_id in self._credentials

    @property
    def provider_ids(self) -> tuple[str, ...]:
        self._ensure_loaded()
        return tuple(self._credentials)

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._credentials)

    def put(self, credential: Credential, *, persist: bool = True) -> Credential:
        """Stores *credential*, stamped with the encryption metadata it
        was written under.

        *persist=False* keeps it in memory only -- the escape hatch an
        unconfigured install uses, chosen explicitly by the caller
        rather than silently degraded to by the store.
        """
        self._ensure_loaded()
        stamped = credential.with_encryption(
            EncryptionMetadata(
                algorithm="fernet",
                key_id=self._key_id,
                encrypted_at=datetime.now(UTC) if persist and self.can_persist else None,
            )
        )
        self._credentials[credential.provider_id] = stamped
        if persist:
            self._save()
        return stamped

    def delete(self, provider_id: str, *, persist: bool = True) -> bool:
        self._ensure_loaded()
        removed = self._credentials.pop(provider_id, None) is not None
        if removed and persist and self.can_persist:
            self._save()
        return removed

    def clear(self, *, persist: bool = True) -> None:
        self._ensure_loaded()
        self._credentials.clear()
        if persist and self.can_persist:
            self._save()

    def public_snapshot(self, *, now: datetime | None = None) -> tuple[dict[str, Any], ...]:
        """Metadata for every credential -- never a token value. The
        only view the REST layer is given."""
        self._ensure_loaded()
        return tuple(c.to_public_dict(now=now) for c in self._credentials.values())

    # ------------------------------------------------------------------
    # Rotation
    # ------------------------------------------------------------------
    def rotate(self, new_secret_key: str, *, new_key_id: str = "") -> int:
        """Re-encrypts every stored credential under *new_secret_key*.

        Decryption still uses the *old* key until the rewrite succeeds,
        so a rotation that fails partway leaves the on-disk file
        readable by the old key rather than half-migrated.
        """
        self._ensure_loaded()  # decrypts with the current key
        if not new_secret_key or new_secret_key == _PLACEHOLDER_KEY:
            raise CredentialEncryptionError("Cannot rotate to an empty or placeholder key.")

        self._secret_key = new_secret_key
        self._key_id = new_key_id or self._key_id
        stamped = EncryptionMetadata(
            algorithm="fernet", key_id=self._key_id, encrypted_at=datetime.now(UTC)
        )
        self._credentials = {
            pid: cred.with_encryption(stamped) for pid, cred in self._credentials.items()
        }
        self._save()
        _logger.info(
            "Rotated {} MCP credential(s) to key {!r}.", len(self._credentials), self._key_id
        )
        return len(self._credentials)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._store_path.exists():
            return
        try:
            raw = json.loads(self._store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as err:
            _logger.warning("Could not read credential store {}: {}", self._store_path, err)
            return

        for row in raw.get("credentials") or []:
            try:
                self._credentials[row["provider_id"]] = self._row_to_credential(row)
            except (KeyError, ValueError, ConfigError) as err:
                # One unreadable record must not make every other
                # credential unavailable -- the same fault isolation the
                # plugin and provider registries already apply.
                _logger.warning(
                    "Skipping unreadable credential for {!r}: {}",
                    row.get("provider_id", "<unknown>"),
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
                f"Could not write credential store {self._store_path}: {err}"
            ) from err

    def _credential_to_row(self, credential: Credential, key: str) -> dict[str, Any]:
        row = credential.to_storage_dict()
        for field_name in _SECRET_FIELDS:
            value = row.get(field_name) or ""
            row[field_name] = encrypt(key, value) if value else ""
        return row

    def _row_to_credential(self, row: dict[str, Any]) -> Credential:
        decoded = dict(row)
        if self._secret_key:
            for field_name in _SECRET_FIELDS:
                value = decoded.get(field_name) or ""
                decoded[field_name] = decrypt(self._secret_key, value) if value else ""
        else:
            # No key: the metadata is still useful for diagnostics, but
            # the tokens are not recoverable -- report that honestly
            # rather than handing back ciphertext that looks like a token.
            for field_name in _SECRET_FIELDS:
                decoded[field_name] = ""
        return Credential.from_storage_dict(decoded)
