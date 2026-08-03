"""Unit tests for ``jarvis.core.lifecycle.crash_recovery.
CrashRecoveryManager`` (Milestone 9 Task Group C)."""

from __future__ import annotations

from pathlib import Path

import pytest


def _settings(tmp_path: Path):
    from jarvis.core.config.settings import Settings

    return Settings(data_dir=tmp_path)


@pytest.mark.asyncio
async def test_fresh_marker_reports_no_crash(tmp_path: Path) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.crash_recovery import CrashRecoveryManager

    manager = CrashRecoveryManager(_settings(tmp_path), EventBus())
    status = await manager.check_and_mark_dirty()

    assert status.recovered_from_crash is False
    assert status.previous_boot_at is None


@pytest.mark.asyncio
async def test_clean_shutdown_then_fresh_boot_reports_no_crash(tmp_path: Path) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.crash_recovery import CrashRecoveryManager

    settings = _settings(tmp_path)
    first = CrashRecoveryManager(settings, EventBus())
    await first.check_and_mark_dirty()
    first.mark_clean()

    second = CrashRecoveryManager(settings, EventBus())
    status = await second.check_and_mark_dirty()

    assert status.recovered_from_crash is False


@pytest.mark.asyncio
async def test_unclean_shutdown_is_detected_on_next_boot(tmp_path: Path) -> None:
    """Simulates a real crash: the first ``CrashRecoveryManager`` marks
    itself dirty at "startup" and is simply abandoned -- never calls
    ``mark_clean()`` -- exactly what a hard process kill looks like."""
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import CrashRecoveredEvent
    from jarvis.core.lifecycle.crash_recovery import CrashRecoveryManager

    settings = _settings(tmp_path)
    first = CrashRecoveryManager(settings, EventBus())
    await first.check_and_mark_dirty()
    # (no mark_clean() -- simulated crash)

    bus2 = EventBus()
    recovered_events: list[CrashRecoveredEvent] = []
    bus2.subscribe(CrashRecoveredEvent, recovered_events.append)
    second = CrashRecoveryManager(settings, bus2)
    status = await second.check_and_mark_dirty()

    assert status.recovered_from_crash is True
    assert status.previous_boot_at is not None
    assert len(recovered_events) == 1


@pytest.mark.asyncio
async def test_corrupt_marker_is_treated_as_no_marker(tmp_path: Path) -> None:
    from jarvis.core.config import paths as _paths
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.crash_recovery import CrashRecoveryManager

    settings = _settings(tmp_path)
    marker_path = _paths.config_dir(settings.resolved_data_dir) / "runtime_state.json"
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text("{not valid json", encoding="utf-8")

    manager = CrashRecoveryManager(settings, EventBus())
    status = await manager.check_and_mark_dirty()  # must not raise

    assert status.recovered_from_crash is False


@pytest.mark.asyncio
async def test_status_property_reflects_last_check(tmp_path: Path) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.lifecycle.crash_recovery import CrashRecoveryManager

    manager = CrashRecoveryManager(_settings(tmp_path), EventBus())
    assert manager.status.recovered_from_crash is False  # default, before any check

    status = await manager.check_and_mark_dirty()
    assert manager.status == status
