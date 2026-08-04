"""Credential store tests -- Milestone 10.5 Task Group D, deliverable 3.

The encryption-at-rest and refuse-to-write-plaintext tests are the
security contract of this task group; they assert against real file
contents rather than mocking the crypto away.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from jarvis.core.mcp.auth.credentials import AuthMethod, Credential
from jarvis.core.mcp.auth.store import CredentialEncryptionError, CredentialStore

_SECRET = "tok_SUPER_SECRET_VALUE"


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def store(tmp_path: Path, key: str) -> CredentialStore:
    return CredentialStore(tmp_path / "creds.json", secret_key=key)


def _cred(provider_id: str = "demo", **kwargs) -> Credential:
    return Credential(
        provider_id=provider_id,
        method=kwargs.pop("method", AuthMethod.API_KEY),
        access_token=kwargs.pop("access_token", _SECRET),
        **kwargs,
    )


# --- Encryption at rest ----------------------------------------------------------


def test_token_is_never_written_in_plaintext(store: CredentialStore, tmp_path: Path) -> None:
    store.put(_cred(refresh_token="refresh_SECRET"))

    raw = (tmp_path / "creds.json").read_text(encoding="utf-8")

    assert _SECRET not in raw
    assert "refresh_SECRET" not in raw
    # Non-secret metadata stays readable for diagnostics.
    assert "demo" in raw


def test_round_trip_through_a_fresh_store_recovers_the_token(tmp_path: Path, key: str) -> None:
    CredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    reloaded = CredentialStore(tmp_path / "creds.json", secret_key=key)

    credential = reloaded.get("demo")
    assert credential is not None
    assert credential.access_token == _SECRET


def test_a_wrong_key_yields_no_credential_rather_than_garbage(tmp_path: Path, key: str) -> None:
    """One unreadable record must not poison the whole store, and it
    must never hand back ciphertext dressed as a token."""
    CredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    wrong = CredentialStore(tmp_path / "creds.json", secret_key=Fernet.generate_key().decode())

    assert wrong.get("demo") is None


def test_reading_without_a_key_exposes_metadata_but_not_tokens(tmp_path: Path, key: str) -> None:
    CredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    keyless = CredentialStore(tmp_path / "creds.json", secret_key="")
    credential = keyless.get("demo")

    assert credential is not None
    assert credential.access_token == ""  # not the ciphertext
    assert credential.provider_id == "demo"


# --- Refusing plaintext ----------------------------------------------------------


def test_placeholder_key_counts_as_no_key(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path / "creds.json", secret_key="CHANGE_ME_TO_A_FERNET_KEY")
    assert store.can_persist is False


def test_persisting_without_a_key_raises_and_writes_nothing(tmp_path: Path) -> None:
    """Writing a token in plaintext is strictly worse than not
    persisting it -- the deliberate divergence from ApiCenterService."""
    store = CredentialStore(tmp_path / "creds.json", secret_key="")

    with pytest.raises(CredentialEncryptionError, match="no encryption key"):
        store.put(_cred())

    assert not (tmp_path / "creds.json").exists()


def test_in_memory_operation_still_works_without_a_key(tmp_path: Path) -> None:
    """An unconfigured install can authenticate for this session; it
    simply will not remember it."""
    store = CredentialStore(tmp_path / "creds.json", secret_key="")

    store.put(_cred(), persist=False)

    credential = store.get("demo")
    assert credential is not None
    assert credential.access_token == _SECRET
    assert not (tmp_path / "creds.json").exists()


# --- CRUD ------------------------------------------------------------------------


def test_get_has_len_and_ids(store: CredentialStore) -> None:
    store.put(_cred("a"))
    store.put(_cred("b"))

    assert store.has("a") is True
    assert store.has("missing") is False
    assert len(store) == 2
    assert store.provider_ids == ("a", "b")


def test_delete_reports_whether_it_existed(store: CredentialStore) -> None:
    store.put(_cred())

    assert store.delete("demo") is True
    assert store.delete("demo") is False


def test_clear_empties_the_store(store: CredentialStore) -> None:
    store.put(_cred("a"))
    store.put(_cred("b"))

    store.clear()

    assert len(store) == 0


def test_put_stamps_encryption_metadata(store: CredentialStore) -> None:
    stored = store.put(_cred())

    assert stored.encryption.algorithm == "fernet"
    assert stored.encryption.key_id == "default"
    assert stored.encryption.encrypted_at is not None


def test_in_memory_put_records_no_encrypted_at(tmp_path: Path) -> None:
    """Claiming an encryption timestamp for something never encrypted
    would misreport the record's actual protection."""
    store = CredentialStore(tmp_path / "c.json", secret_key="")
    stored = store.put(_cred(), persist=False)

    assert stored.encryption.encrypted_at is None


def test_public_snapshot_never_contains_a_token(store: CredentialStore) -> None:
    store.put(_cred(refresh_token="refresh_SECRET"))

    payload = store.public_snapshot()

    assert _SECRET not in str(payload)
    assert "refresh_SECRET" not in str(payload)
    assert payload[0]["has_access_token"] is True


# --- Rotation --------------------------------------------------------------------


def test_rotate_re_encrypts_every_credential(tmp_path: Path, key: str) -> None:
    store = CredentialStore(tmp_path / "creds.json", secret_key=key)
    store.put(_cred("a"))
    store.put(_cred("b"))
    new_key = Fernet.generate_key().decode()

    rotated = store.rotate(new_key, new_key_id="k2")

    assert rotated == 2
    # Readable under the new key, not the old one.
    reopened = CredentialStore(tmp_path / "creds.json", secret_key=new_key)
    credential = reopened.get("a")
    assert credential is not None
    assert credential.access_token == _SECRET
    assert credential.encryption.key_id == "k2"

    stale = CredentialStore(tmp_path / "creds.json", secret_key=key)
    assert stale.get("a") is None


def test_rotate_to_an_empty_or_placeholder_key_is_refused(store: CredentialStore) -> None:
    store.put(_cred())

    with pytest.raises(CredentialEncryptionError, match="empty or placeholder"):
        store.rotate("")
    with pytest.raises(CredentialEncryptionError, match="empty or placeholder"):
        store.rotate("CHANGE_ME_TO_A_FERNET_KEY")


# --- Corruption tolerance --------------------------------------------------------


def test_unreadable_file_degrades_to_empty_rather_than_crashing(tmp_path: Path, key: str) -> None:
    (tmp_path / "creds.json").write_text("{not json", encoding="utf-8")

    store = CredentialStore(tmp_path / "creds.json", secret_key=key)

    assert len(store) == 0


def test_one_corrupt_record_does_not_hide_the_others(tmp_path: Path, key: str) -> None:
    store = CredentialStore(tmp_path / "creds.json", secret_key=key)
    store.put(_cred("good"))

    import json

    raw = json.loads((tmp_path / "creds.json").read_text(encoding="utf-8"))
    raw["credentials"].append({"provider_id": "bad", "access_token": "not-valid-ciphertext"})
    (tmp_path / "creds.json").write_text(json.dumps(raw), encoding="utf-8")

    reloaded = CredentialStore(tmp_path / "creds.json", secret_key=key)

    assert reloaded.has("good") is True
    assert reloaded.has("bad") is False
