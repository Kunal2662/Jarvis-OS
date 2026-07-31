"""Unit tests for :class:`DeveloperModeService` -- Milestone 5, section 10A."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.core.exceptions import InvalidAdminPasswordError
from jarvis.services.developer_mode_service import DeveloperModeService
from jarvis.services.settings_service import SettingsService


@pytest.fixture()
def dev_mode(tmp_path: Path) -> DeveloperModeService:
    settings = Settings(data_dir=tmp_path)
    settings_service = SettingsService(settings, env_file=tmp_path / ".env")
    return DeveloperModeService(settings, settings_service)


def test_not_configured_initially(dev_mode: DeveloperModeService) -> None:
    assert dev_mode.is_configured() is False
    assert dev_mode.is_unlocked() is False


@pytest.mark.asyncio
async def test_set_password_then_unlock(dev_mode: DeveloperModeService) -> None:
    await dev_mode.set_password("correct-horse")
    assert dev_mode.is_configured() is True

    dev_mode.unlock("correct-horse")
    assert dev_mode.is_unlocked() is True
    assert dev_mode.remaining_seconds() > 0


@pytest.mark.asyncio
async def test_wrong_password_raises(dev_mode: DeveloperModeService) -> None:
    await dev_mode.set_password("correct-horse")
    with pytest.raises(InvalidAdminPasswordError):
        dev_mode.unlock("wrong-password")
    assert dev_mode.is_unlocked() is False


@pytest.mark.asyncio
async def test_too_short_password_rejected(dev_mode: DeveloperModeService) -> None:
    with pytest.raises(InvalidAdminPasswordError):
        await dev_mode.set_password("abc")


@pytest.mark.asyncio
async def test_lock_ends_session(dev_mode: DeveloperModeService) -> None:
    await dev_mode.set_password("correct-horse")
    dev_mode.unlock("correct-horse")
    assert dev_mode.is_unlocked() is True
    dev_mode.lock()
    assert dev_mode.is_unlocked() is False


@pytest.mark.asyncio
async def test_password_persisted_across_service_instances(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    settings_service = SettingsService(settings, env_file=tmp_path / ".env")
    dev_mode = DeveloperModeService(settings, settings_service)
    await dev_mode.set_password("correct-horse")

    # A second service instance against the same settings object should see it too.
    dev_mode_2 = DeveloperModeService(settings, settings_service)
    assert dev_mode_2.is_configured() is True
    dev_mode_2.unlock("correct-horse")
    assert dev_mode_2.is_unlocked() is True
