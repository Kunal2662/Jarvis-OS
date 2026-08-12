"""Connector credential store tests -- Milestone 12 Task Group B, Phase 1.

Mirrors ``test_mcp_auth_store.py``'s shape -- real temp-file
persistence throughout, asserting against actual file contents rather
than mocking the crypto away. ``ConnectorCredentialStore`` has a
smaller surface than MCP's own ``CredentialStore`` (no ``rotate``, no
``clear``, no ``__len__``) -- only what this task group's Logic
Contract commits to is tested here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from jarvis.core.connectivity.credential_store import (
    ConnectorCredential,
    ConnectorCredentialStore,
    CredentialEncryptionError,
)

_SECRET = "ha_LONG_LIVED_TOKEN"


@pytest.fixture
def key() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def store(tmp_path: Path, key: str) -> ConnectorCredentialStore:
    return ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key)


def _cred(connector_type: str = "home_assistant", **kwargs) -> ConnectorCredential:
    secrets = kwargs.pop("secrets", {"access_token": _SECRET})
    return ConnectorCredential(connector_type=connector_type, secrets=secrets, **kwargs)


# --- Encryption at rest ------------------------------------------------------


def test_secret_is_never_written_in_plaintext(
    store: ConnectorCredentialStore, tmp_path: Path
) -> None:
    store.put(_cred(secrets={"access_token": _SECRET, "refresh_token": "refresh_SECRET"}))

    raw = (tmp_path / "creds.json").read_text(encoding="utf-8")

    assert _SECRET not in raw
    assert "refresh_SECRET" not in raw
    assert "home_assistant" in raw


def test_round_trip_through_a_fresh_store_recovers_the_secret(tmp_path: Path, key: str) -> None:
    ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    reloaded = ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key)

    credential = reloaded.get("home_assistant")
    assert credential is not None
    assert credential.secrets["access_token"] == _SECRET


def test_a_wrong_key_yields_no_credential_rather_than_garbage(tmp_path: Path, key: str) -> None:
    ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    wrong = ConnectorCredentialStore(
        tmp_path / "creds.json", secret_key=Fernet.generate_key().decode()
    )

    assert wrong.get("home_assistant") is None


def test_reading_without_a_key_exposes_metadata_but_not_secrets(tmp_path: Path, key: str) -> None:
    ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key).put(_cred())

    keyless = ConnectorCredentialStore(tmp_path / "creds.json", secret_key="")
    credential = keyless.get("home_assistant")

    assert credential is not None
    assert credential.secrets["access_token"] == ""
    assert credential.connector_type == "home_assistant"


# --- Refusing plaintext -------------------------------------------------------


def test_placeholder_key_counts_as_no_key(tmp_path: Path) -> None:
    store = ConnectorCredentialStore(
        tmp_path / "creds.json", secret_key="CHANGE_ME_TO_A_FERNET_KEY"
    )
    assert store.can_persist is False


def test_persisting_without_a_key_raises_and_writes_nothing(tmp_path: Path) -> None:
    store = ConnectorCredentialStore(tmp_path / "creds.json", secret_key="")

    with pytest.raises(CredentialEncryptionError, match="no encryption key"):
        store.put(_cred())

    assert not (tmp_path / "creds.json").exists()


def test_in_memory_operation_still_works_without_a_key(tmp_path: Path) -> None:
    store = ConnectorCredentialStore(tmp_path / "creds.json", secret_key="")

    store.put(_cred(), persist=False)

    credential = store.get("home_assistant")
    assert credential is not None
    assert credential.secrets["access_token"] == _SECRET
    assert not (tmp_path / "creds.json").exists()


# --- CRUD ----------------------------------------------------------------------


def test_get_has_and_connector_types(store: ConnectorCredentialStore) -> None:
    store.put(_cred("home_assistant"))
    store.put(_cred("mqtt", secrets={"username": "u", "password": "p"}))

    assert store.has("home_assistant") is True
    assert store.has("missing") is False
    assert store.connector_types == ("home_assistant", "mqtt")


def test_delete_reports_whether_it_existed(store: ConnectorCredentialStore) -> None:
    store.put(_cred())

    assert store.delete("home_assistant") is True
    assert store.delete("home_assistant") is False


def test_put_stamps_encryption_metadata(store: ConnectorCredentialStore) -> None:
    stored = store.put(_cred())

    assert stored.encryption.algorithm == "fernet"
    assert stored.encryption.key_id == "default"
    assert stored.encryption.encrypted_at is not None


def test_in_memory_put_records_no_encrypted_at(tmp_path: Path) -> None:
    store = ConnectorCredentialStore(tmp_path / "c.json", secret_key="")
    stored = store.put(_cred(), persist=False)

    assert stored.encryption.encrypted_at is None


def test_public_snapshot_never_contains_a_secret(store: ConnectorCredentialStore) -> None:
    store.put(_cred(secrets={"access_token": _SECRET, "refresh_token": "refresh_SECRET"}))

    payload = store.public_snapshot()

    assert _SECRET not in str(payload)
    assert "refresh_SECRET" not in str(payload)
    assert payload[0]["has_secrets"] is True
    assert payload[0]["secret_keys"] == ["access_token", "refresh_token"]


# --- Corruption tolerance -------------------------------------------------------


def test_unreadable_file_degrades_to_empty_rather_than_crashing(tmp_path: Path, key: str) -> None:
    (tmp_path / "creds.json").write_text("{not json", encoding="utf-8")

    store = ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key)

    assert store.connector_types == ()


def test_one_corrupt_record_does_not_hide_the_others(tmp_path: Path, key: str) -> None:
    store = ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key)
    store.put(_cred("home_assistant"))

    raw = json.loads((tmp_path / "creds.json").read_text(encoding="utf-8"))
    raw["credentials"].append({"secrets": {"access_token": "not-valid-ciphertext"}})
    (tmp_path / "creds.json").write_text(json.dumps(raw), encoding="utf-8")

    reloaded = ConnectorCredentialStore(tmp_path / "creds.json", secret_key=key)

    assert reloaded.has("home_assistant") is True


# --- Redaction -------------------------------------------------------------------


def test_repr_redacts_secrets() -> None:
    credential = _cred(secrets={"access_token": _SECRET})

    rendered = repr(credential)

    assert _SECRET not in rendered
    assert "***redacted***" in rendered
    assert "home_assistant" in rendered


def test_revoke_clears_secrets() -> None:
    revoked = _cred().revoke()

    assert revoked.revoked is True
    assert revoked.secrets == {}
    assert revoked.has_secrets is False
