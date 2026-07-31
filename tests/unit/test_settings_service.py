"""Unit tests for :class:`SettingsService.set_env`."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.core.exceptions import ServiceError
from jarvis.services.settings_service import SettingsService


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("JARVIS_UI_THEME=jarvis\nJARVIS_LOG_LEVEL=INFO\n", encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_set_env_updates_existing_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    await svc.set_env("JARVIS_UI_THEME", "dark")

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_UI_THEME=dark" in text
    assert "JARVIS_UI_THEME=jarvis" not in text
    assert "JARVIS_LOG_LEVEL=INFO" in text  # untouched


@pytest.mark.asyncio
async def test_set_env_appends_missing_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    await svc.set_env("JARVIS_LOG_JSON", "true")

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_LOG_JSON=true" in text


@pytest.mark.asyncio
async def test_set_env_rejects_non_whitelisted_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    with pytest.raises(ServiceError):
        await svc.set_env("JARVIS_SECRET_KEY", "hax")


@pytest.mark.asyncio
async def test_set_env_creates_file_if_missing(tmp_path: Path) -> None:
    p = tmp_path / ".env"
    settings = Settings()
    svc = SettingsService(settings, env_file=p)

    await svc.set_env("JARVIS_UI_THEME", "light")

    assert p.exists()
    assert "JARVIS_UI_THEME=light" in p.read_text(encoding="utf-8")
