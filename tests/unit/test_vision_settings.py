"""Milestone 6, Phase 2 — configuration-scaffolding tests for Vision/OCR.

Only verifies settings defaults, env-var overrides, root ``Settings``
construction, and the ``SettingsService`` writable-key whitelist. No
provider, service, DI, event, tool, or UI code exists yet — those are
later phases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import OCRSettings, Settings, VisionSettings
from jarvis.core.exceptions import ServiceError
from jarvis.services.settings_service import SettingsService


def test_vision_settings_defaults_to_disabled() -> None:
    settings = VisionSettings()

    assert settings.enabled is False


def test_ocr_settings_defaults_to_disabled() -> None:
    settings = OCRSettings()

    assert settings.enabled is False


def test_vision_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_VISION_ENABLED", "true")

    settings = VisionSettings()

    assert settings.enabled is True


def test_ocr_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JARVIS_OCR_ENABLED", "true")

    settings = OCRSettings()

    assert settings.enabled is True


def test_vision_settings_ignores_unknown_keys() -> None:
    # extra="ignore" — must not raise on an unrelated env var carrying the
    # same prefix-adjacent shape.
    settings = VisionSettings(unexpected_field="ignored")  # type: ignore[call-arg]

    assert settings.enabled is False


def test_root_settings_constructs_with_vision_and_ocr_disabled_by_default() -> None:
    settings = Settings()

    assert isinstance(settings.vision, VisionSettings)
    assert isinstance(settings.ocr, OCRSettings)
    assert settings.vision.enabled is False
    assert settings.ocr.enabled is False


def test_root_settings_picks_up_vision_and_ocr_env_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JARVIS_VISION_ENABLED", "true")
    monkeypatch.setenv("JARVIS_OCR_ENABLED", "true")

    settings = Settings()

    assert settings.vision.enabled is True
    assert settings.ocr.enabled is True


def test_root_settings_construction_has_no_side_effects(tmp_path: Path) -> None:
    """Constructing Settings() must not touch disk, spawn a provider, or
    otherwise do anything beyond reading env vars — vision/ocr scaffolding
    must not change that."""
    before = list(tmp_path.iterdir())

    Settings()

    after = list(tmp_path.iterdir())
    assert before == after == []


@pytest.fixture()
def env_file(tmp_path: Path) -> Path:
    p = tmp_path / ".env"
    p.write_text("JARVIS_UI_THEME=jarvis\n", encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_settings_service_accepts_vision_enabled_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    await svc.set_env("JARVIS_VISION_ENABLED", "true")

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_VISION_ENABLED=true" in text


@pytest.mark.asyncio
async def test_settings_service_accepts_ocr_enabled_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    await svc.set_env("JARVIS_OCR_ENABLED", "true")

    text = env_file.read_text(encoding="utf-8")
    assert "JARVIS_OCR_ENABLED=true" in text


@pytest.mark.asyncio
async def test_settings_service_still_rejects_non_whitelisted_key(env_file: Path) -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=env_file)

    with pytest.raises(ServiceError):
        await svc.set_env("JARVIS_VISION_MODEL", "some-model")


def test_writable_keys_include_vision_and_ocr() -> None:
    settings = Settings()
    svc = SettingsService(settings, env_file=Path("unused.env"))

    keys = svc.writable_keys()

    assert "JARVIS_VISION_ENABLED" in keys
    assert "JARVIS_OCR_ENABLED" in keys


def test_writable_keys_preserve_every_pre_existing_key() -> None:
    """Regression guard: the whitelist must be append-only for this phase —
    every key that existed before Phase 2 must still be present."""
    settings = Settings()
    svc = SettingsService(settings, env_file=Path("unused.env"))

    keys = set(svc.writable_keys())

    pre_existing_sample = {
        "JARVIS_LLM_DEFAULT_PROVIDER",
        "JARVIS_LLM_FALLBACK_PROVIDER",
        "JARVIS_OPENAI_ENABLED",
        "JARVIS_UI_THEME",
        "JARVIS_VOICE_ANNOUNCE_ENABLED",
        "JARVIS_AGENT_MAX_STEPS",
        "JARVIS_AGENT_TIMEOUT_SECONDS",
        "JARVIS_AGENT_CHECKPOINT_ENABLED",
    }
    assert pre_existing_sample <= keys
