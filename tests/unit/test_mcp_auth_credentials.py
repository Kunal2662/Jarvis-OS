"""Credential model tests -- Milestone 10.5 Task Group D, deliverable 2.

The redaction and serialization tests here are the ones that matter
most: they are what stop a token reaching a log line or a REST body.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from jarvis.core.mcp.auth.credentials import (
    REFRESHABLE_METHODS,
    STATIC_METHODS,
    AuthMethod,
    Credential,
    CredentialStatus,
    EncryptionMetadata,
)

_SECRET = "tok_SUPER_SECRET_VALUE"
_NOW = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def _cred(**kwargs) -> Credential:
    return Credential(
        provider_id=kwargs.pop("provider_id", "demo"),
        method=kwargs.pop("method", AuthMethod.BEARER_TOKEN),
        access_token=kwargs.pop("access_token", _SECRET),
        **kwargs,
    )


# --- Redaction -----------------------------------------------------------------


def test_repr_redacts_both_tokens() -> None:
    """A stray ``logger.info("... {}", credential)`` must not leak."""
    credential = _cred(refresh_token="refresh_SECRET")

    rendered = repr(credential)

    assert _SECRET not in rendered
    assert "refresh_SECRET" not in rendered
    assert "***redacted***" in rendered
    assert "demo" in rendered  # non-secret context survives


def test_str_redacts_too() -> None:
    assert _SECRET not in str(_cred())


def test_repr_of_an_empty_token_is_not_falsely_redacted() -> None:
    """Reporting a redaction marker where there is no secret would
    misrepresent an unauthenticated credential as an authenticated one."""
    rendered = repr(Credential(provider_id="demo", method=AuthMethod.NONE))
    assert "***redacted***" not in rendered


# --- Serialization -------------------------------------------------------------


def test_public_dict_never_contains_a_token() -> None:
    payload = _cred(refresh_token="refresh_SECRET").to_public_dict(now=_NOW)

    assert _SECRET not in str(payload)
    assert "refresh_SECRET" not in str(payload)
    assert payload["has_access_token"] is True
    assert payload["has_refresh_token"] is True


def test_storage_dict_does_contain_tokens() -> None:
    """The store needs the real material; the distinction between the
    two serializers is the whole safety mechanism."""
    payload = _cred().to_storage_dict()
    assert payload["access_token"] == _SECRET


def test_storage_round_trip_preserves_everything() -> None:
    original = _cred(
        method=AuthMethod.OAUTH2,
        refresh_token="r",
        expires_at=_NOW,
        scopes=("repo:read",),
        account_id="acct-1",
        encryption=EncryptionMetadata(key_id="k2", encrypted_at=_NOW),
    )

    restored = Credential.from_storage_dict(original.to_storage_dict())

    assert restored.access_token == original.access_token
    assert restored.refresh_token == original.refresh_token
    assert restored.scopes == original.scopes
    assert restored.account_id == "acct-1"
    assert restored.encryption.key_id == "k2"
    assert restored.method is AuthMethod.OAUTH2


def test_from_storage_dict_tolerates_a_malformed_expiry() -> None:
    restored = Credential.from_storage_dict(
        {"provider_id": "demo", "method": "api_key", "expires_at": "not-a-date"}
    )
    assert restored.expires_at is None


# --- Expiry ---------------------------------------------------------------------


def test_no_expiry_never_expires() -> None:
    credential = _cred(expires_at=None)

    assert credential.is_expired(now=_NOW) is False
    assert credential.seconds_until_expiry(now=_NOW) is None
    assert credential.status(now=_NOW) is CredentialStatus.ACTIVE


def test_expired_credential_reports_expired() -> None:
    credential = _cred(expires_at=_NOW - timedelta(seconds=1))

    assert credential.is_expired(now=_NOW) is True
    assert credential.status(now=_NOW) is CredentialStatus.EXPIRED
    assert credential.is_valid(now=_NOW) is False


def test_expiry_at_the_exact_boundary_counts_as_expired() -> None:
    assert _cred(expires_at=_NOW).is_expired(now=_NOW) is True


def test_expiring_soon_warns_before_it_breaks() -> None:
    credential = _cred(expires_at=_NOW + timedelta(seconds=60))

    assert credential.status(now=_NOW, warning_seconds=300) is CredentialStatus.EXPIRING
    # Still usable -- a warning is not a failure.
    assert credential.is_valid(now=_NOW) is True


def test_naive_expiry_is_normalized_rather_than_crashing() -> None:
    """JSON and SQLite both hand back naive datetimes; comparing one
    against an aware 'now' would raise without normalization."""
    credential = _cred(expires_at=datetime(2026, 8, 4, 11, 0))

    assert credential.is_expired(now=_NOW) is True


def test_missing_token_reports_missing() -> None:
    assert _cred(access_token="").status(now=_NOW) is CredentialStatus.MISSING


def test_none_method_without_a_token_is_still_active() -> None:
    """A local peer needing no credential is authenticated by
    definition -- reporting it MISSING would be wrong."""
    credential = Credential(provider_id="demo", method=AuthMethod.NONE)
    assert credential.status(now=_NOW) is CredentialStatus.ACTIVE


# --- Transitions ----------------------------------------------------------------


def test_refresh_keeps_the_existing_refresh_token_when_none_returned() -> None:
    """Dropping it would silently make the credential unrefreshable."""
    original = _cred(method=AuthMethod.OAUTH2, refresh_token="keep_me")

    refreshed = original.with_refreshed("new_access")

    assert refreshed.access_token == "new_access"
    assert refreshed.refresh_token == "keep_me"


def test_refresh_replaces_the_refresh_token_when_one_is_returned() -> None:
    original = _cred(method=AuthMethod.OAUTH2, refresh_token="old")
    assert original.with_refreshed("a", refresh_token="new").refresh_token == "new"


def test_refresh_clears_a_prior_revocation() -> None:
    revoked = _cred(method=AuthMethod.OAUTH2, refresh_token="r").revoke()
    assert revoked.with_refreshed("fresh").revoked is False


def test_revoke_clears_both_tokens() -> None:
    """A revoked credential still holding its secret is a credential
    waiting to leak."""
    revoked = _cred(refresh_token="r").revoke()

    assert revoked.revoked is True
    assert revoked.access_token == ""
    assert revoked.refresh_token == ""
    assert revoked.status(now=_NOW) is CredentialStatus.REVOKED


def test_credential_is_frozen() -> None:
    with pytest.raises(Exception):  # noqa: B017 -- FrozenInstanceError
        _cred().access_token = "other"  # type: ignore[misc]


# --- Refreshability -------------------------------------------------------------


def test_only_refreshable_methods_with_a_token_are_refreshable() -> None:
    assert _cred(method=AuthMethod.OAUTH2, refresh_token="r").is_refreshable is True
    # OAuth without a refresh token cannot actually refresh.
    assert _cred(method=AuthMethod.OAUTH2).is_refreshable is False
    # A static token never can, even if one were somehow set.
    assert _cred(method=AuthMethod.API_KEY, refresh_token="r").is_refreshable is False


def test_method_sets_are_disjoint() -> None:
    assert frozenset() == STATIC_METHODS & REFRESHABLE_METHODS
    assert AuthMethod.NONE not in STATIC_METHODS | REFRESHABLE_METHODS
