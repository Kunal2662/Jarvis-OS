"""Cryptographic helpers around the app's Fernet secret key."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from jarvis.core.exceptions import ConfigError


def build_fernet(secret_key: str) -> Fernet:
    """Build a :class:`Fernet` from the base64 key stored in settings."""
    try:
        return Fernet(secret_key.encode("utf-8"))
    except (ValueError, TypeError) as err:
        raise ConfigError(
            "JARVIS_SECRET_KEY is not a valid Fernet key. Generate one with:"
            ' python -c "from cryptography.fernet import Fernet;'
            ' print(Fernet.generate_key().decode())"'
        ) from err


def encrypt(secret_key: str, plaintext: str) -> str:
    return build_fernet(secret_key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(secret_key: str, token: str) -> str:
    try:
        return build_fernet(secret_key).decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as err:  # pragma: no cover — trivial rethrow
        raise ConfigError("Cannot decrypt: invalid token or wrong key.") from err
