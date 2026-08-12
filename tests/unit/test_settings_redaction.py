"""Unit tests for ``SettingsService``'s secret redaction -- M8 Phase 2.

``snapshot()`` and ``public_snapshot()`` are deliberately two methods, not
one with a flag: the PySide6 Configuration Manager runs inside the same
trust boundary as the ``.env`` file it displays and legitimately wants the
real values, while anything crossing a process boundary must not have
them. These tests pin the difference, and pin *why* redaction works by key
name rather than by type -- ``IntegrationSettings.clients`` is a plain
``dict[str, dict[str, str]]``, so nothing about its type says "secret".
"""

from __future__ import annotations

from pydantic import SecretStr

from jarvis.core.config.settings import Settings
from jarvis.services.settings_service import (
    REDACTED,
    SettingsService,
    _is_secret_key,
    _redact,
)


def _service() -> SettingsService:
    settings = Settings()
    settings.openai.api_key = SecretStr("sk-live-secret")
    settings.integrations.clients = {
        "google": {"client_id": "public-id", "client_secret": "GOCSPX-secret"}
    }
    return SettingsService(settings)


class TestIsSecretKey:
    def test_matches_every_marker(self) -> None:
        for key in (
            "client_secret",
            "password",
            "api_key",
            "apiKey",
            "access_token",
            "credential",
            "private_key",
        ):
            assert _is_secret_key(key), key

    def test_is_case_insensitive(self) -> None:
        assert _is_secret_key("CLIENT_SECRET")
        assert _is_secret_key("Api_Key")

    def test_matches_a_marker_anywhere_in_the_name(self) -> None:
        # `refresh_token_expires_at` is not itself a secret, but erring
        # towards redaction on a name that contains `token` is the right
        # side to be wrong on.
        assert _is_secret_key("refresh_token_expires_at")

    def test_leaves_ordinary_keys_alone(self) -> None:
        for key in ("client_id", "theme", "base_url", "model", "enabled", "provider"):
            assert not _is_secret_key(key), key


class TestRedact:
    def test_replaces_a_scalar_secret(self) -> None:
        assert _redact("hunter2", key="password") == REDACTED

    def test_recurses_into_nested_dicts(self) -> None:
        value = {"google": {"client_id": "keep", "client_secret": "hide"}}
        assert _redact(value) == {"google": {"client_id": "keep", "client_secret": REDACTED}}

    def test_recurses_into_lists(self) -> None:
        value = {"accounts": [{"name": "a", "api_key": "hide"}, {"name": "b", "api_key": "hide"}]}
        redacted = _redact(value)
        assert [entry["api_key"] for entry in redacted["accounts"]] == [REDACTED, REDACTED]
        assert [entry["name"] for entry in redacted["accounts"]] == ["a", "b"]

    def test_redacts_a_whole_subtree_under_a_secret_key(self) -> None:
        # A dict *named* like a secret is replaced entirely rather than
        # walked -- its keys could be anything, and one of them being
        # innocuous does not make the structure safe to publish.
        assert _redact({"credentials": {"anything": "here"}}) == {"credentials": REDACTED}

    def test_leaves_non_secret_scalars_untouched(self) -> None:
        assert _redact({"theme": "jarvis", "port": 8000, "enabled": True}) == {
            "theme": "jarvis",
            "port": 8000,
            "enabled": True,
        }

    def test_is_pure(self) -> None:
        original = {"api_key": "secret", "nested": {"password": "p"}}
        _redact(original)
        assert original == {"api_key": "secret", "nested": {"password": "p"}}


class TestSnapshots:
    def test_public_snapshot_hides_the_plain_dict_oauth_secret(self) -> None:
        """The leak this phase found: `clients` is not a SecretStr."""
        data = _service().public_snapshot()

        assert data["integrations"]["clients"]["google"]["client_secret"] == REDACTED
        assert data["integrations"]["clients"]["google"]["client_id"] == "public-id"

    def test_public_snapshot_hides_secretstr_fields_too(self) -> None:
        assert "sk-live-secret" not in str(_service().public_snapshot())

    def test_snapshot_keeps_real_values_for_in_process_callers(self) -> None:
        # The Configuration Manager view needs the real client id/secret
        # to show what is configured; it runs inside the trust boundary.
        clients = _service().snapshot()["integrations"]["clients"]
        assert clients["google"]["client_secret"] == "GOCSPX-secret"

    def test_the_two_snapshots_have_identical_structure(self) -> None:
        """Redaction changes values, never shape -- a UI can render either."""

        def shape(value: object) -> object:
            if isinstance(value, dict):
                return {k: shape(v) for k, v in sorted(value.items())}
            if isinstance(value, list):
                return [shape(v) for v in value]
            return type(value).__name__

        service = _service()
        assert shape(service.snapshot()) == shape(service.public_snapshot())

    def test_public_snapshot_is_json_ready(self) -> None:
        import json

        json.dumps(_service().public_snapshot())
