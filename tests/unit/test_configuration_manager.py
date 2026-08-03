"""Unit tests for ``jarvis.core.lifecycle.configuration_manager.
ConfigurationManager`` (Milestone 9 Task Group B)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def loaded_settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_OPENAI_ENABLED", "false")
    monkeypatch.setenv("JARVIS_OLLAMA_ENABLED", "true")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.mark.asyncio
async def test_reload_applies_changed_safe_field_and_publishes_event(
    loaded_settings, monkeypatch
) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import ConfigurationUpdatedEvent
    from jarvis.core.lifecycle.configuration_manager import ConfigurationManager

    assert loaded_settings.update.channel == "stable"

    bus = EventBus()
    published: list[ConfigurationUpdatedEvent] = []
    bus.subscribe(ConfigurationUpdatedEvent, published.append)

    manager = ConfigurationManager(loaded_settings, bus)

    monkeypatch.setenv("JARVIS_UPDATE_CHANNEL", "beta")
    changed = await manager.reload()

    assert "update.channel" in changed
    assert loaded_settings.update.channel == "beta"  # mutated in place
    assert len(published) == 1
    assert "update.channel" in published[0].keys


@pytest.mark.asyncio
async def test_reload_ignores_unsafe_section_changes(loaded_settings, monkeypatch) -> None:
    """``db`` is not in ``SAFE_RELOAD_SECTIONS`` -- a changed env var
    there must never mutate the live, already-injected ``Settings``."""
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.configuration_manager import ConfigurationManager

    original_url = loaded_settings.db.url
    bus = EventBus()
    manager = ConfigurationManager(loaded_settings, bus)

    monkeypatch.setenv("JARVIS_DB_URL", "sqlite+aiosqlite:///./should-not-apply.db")
    changed = await manager.reload()

    assert not any(key.startswith("db.") for key in changed)
    assert loaded_settings.db.url == original_url


@pytest.mark.asyncio
async def test_reload_with_no_changes_publishes_nothing(loaded_settings) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import ConfigurationUpdatedEvent
    from jarvis.core.lifecycle.configuration_manager import ConfigurationManager

    bus = EventBus()
    published: list[ConfigurationUpdatedEvent] = []
    bus.subscribe(ConfigurationUpdatedEvent, published.append)

    manager = ConfigurationManager(loaded_settings, bus)
    changed = await manager.reload()

    assert changed == ()
    assert published == []


def test_feature_flags_reflects_provider_enabled_bools(loaded_settings) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.configuration_manager import ConfigurationManager

    manager = ConfigurationManager(loaded_settings, EventBus())
    flags = manager.feature_flags()

    assert flags["openai"] is False
    assert flags["ollama"] is True
    assert "db" not in flags  # DatabaseSettings has no `enabled` field


def test_safe_reload_sections_matches_documented_set(loaded_settings) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.configuration_manager import ConfigurationManager

    manager = ConfigurationManager(loaded_settings, EventBus())
    assert manager.safe_reload_sections() == (
        "dev_mode",
        "memory",
        "ui",
        "update",
        "voice_announce",
    )
