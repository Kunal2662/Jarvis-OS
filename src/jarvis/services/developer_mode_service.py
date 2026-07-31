"""Developer Mode gate (Milestone 5, section 10A).

JARVIS itself never requires a password to launch -- only entering
Developer Mode (Dashboard, API Center, Update Center, Module/Plugin
managers, ...) does. The password is stored salted+hashed (PBKDF2-HMAC,
never plaintext) via the same ``.env``-persistence path every other
setting uses (:class:`SettingsService`), so there is no bespoke storage
format to keep secure.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import TYPE_CHECKING

from jarvis.core.exceptions import InvalidAdminPasswordError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.settings_service import SettingsService

_logger = get_logger("jarvis.services.developer_mode")

_ITERATIONS = 200_000


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    # Constant-time comparison -- audit fix (Milestones 0-5 completion
    # audit): the previous `candidate.hex() == digest_hex` short-circuits
    # on the first mismatched character, which is a textbook timing-attack
    # anti-pattern for any secret comparison, password hashes included.
    return hmac.compare_digest(candidate.hex(), digest_hex)


class DeveloperModeService:
    def __init__(self, settings: Settings, settings_service: SettingsService) -> None:
        self._settings = settings
        self._settings_service = settings_service
        self._unlocked_until: float = 0.0

    # ------------------------------------------------------------------
    def is_configured(self) -> bool:
        return bool(self._settings.dev_mode.password_hash.get_secret_value())

    async def set_password(self, new_password: str) -> None:
        if len(new_password) < 6:
            raise InvalidAdminPasswordError("Administrator password must be at least 6 characters.")
        salt = os.urandom(16)
        stored = _hash_password(new_password, salt)
        await self._settings_service.set_env("JARVIS_DEV_MODE_PASSWORD_HASH", stored)
        # Reflect immediately in this session without requiring a restart.
        from pydantic import SecretStr

        self._settings.dev_mode.password_hash = SecretStr(stored)
        _logger.info("Developer Mode administrator password configured.")

    def verify(self, password: str) -> bool:
        stored = self._settings.dev_mode.password_hash.get_secret_value()
        if not stored:
            return False
        return _verify_password(password, stored)

    def unlock(self, password: str) -> None:
        if not self.verify(password):
            raise InvalidAdminPasswordError("Incorrect administrator password.")
        timeout_s = self._settings.dev_mode.session_timeout_minutes * 60
        self._unlocked_until = time.monotonic() + timeout_s
        _logger.info(
            "Developer Mode unlocked for {} minutes.",
            self._settings.dev_mode.session_timeout_minutes,
        )

    def lock(self) -> None:
        self._unlocked_until = 0.0

    def is_unlocked(self) -> bool:
        return time.monotonic() < self._unlocked_until

    def remaining_seconds(self) -> float:
        return max(0.0, self._unlocked_until - time.monotonic())
