"""Unit tests for :class:`UpdateService` -- Milestone 5, sections 10C/10D/10E/10F."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.config.settings import Settings
from jarvis.domain.updates.models import UpdateChannel, UpdatePhase
from jarvis.services.update_service import UpdateService
from jarvis.services.voice_announcement_service import VoiceAnnouncementService


@pytest.fixture()
def service(tmp_path: Path) -> UpdateService:
    settings = Settings(data_dir=tmp_path)
    return UpdateService(settings, voice_announcer=VoiceAnnouncementService(settings))


def test_version_history_has_release_notes_per_channel(service: UpdateService) -> None:
    for channel in UpdateChannel:
        notes = service.version_history(channel)
        assert len(notes) >= 1
        assert notes[0].channel is channel


def test_check_for_updates_finds_a_newer_version(service: UpdateService) -> None:
    latest = service.check_for_updates(UpdateChannel.STABLE)
    assert latest is not None
    assert latest.version != service.current_version


@pytest.mark.asyncio
async def test_successful_update_creates_restore_point_and_advances_version(
    service: UpdateService,
) -> None:
    before = service.current_version
    session = await service.run_update(UpdateChannel.STABLE)

    assert session.succeeded is True
    assert session.phase is UpdatePhase.COMPLETED
    assert session.restore_point_id is not None
    assert service.current_version != before
    assert len(service.list_restore_points()) == 1


@pytest.mark.asyncio
async def test_failed_update_triggers_automatic_rollback(service: UpdateService) -> None:
    before = service.current_version
    session = await service.run_update(UpdateChannel.NIGHTLY, simulate_failure=True)

    assert session.succeeded is False
    assert session.phase is UpdatePhase.FAILED
    assert session.rollback_report is not None
    assert session.rollback_report.succeeded is True
    # Version must not have advanced on a failed+rolled-back update.
    assert service.current_version == before


@pytest.mark.asyncio
async def test_update_emits_phase_events(tmp_path: Path) -> None:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.events.events import UpdatePhaseEvent

    settings = Settings(data_dir=tmp_path)
    bus = EventBus()
    received: list[str] = []

    async def _on_phase(evt: UpdatePhaseEvent) -> None:
        received.append(evt.phase)

    bus.subscribe(UpdatePhaseEvent, _on_phase)
    service = UpdateService(settings, event_bus=bus)
    await service.run_update(UpdateChannel.STABLE)

    assert "downloading" in received
    assert "installing" in received
    assert "update_completed" in received


@pytest.mark.asyncio
async def test_manual_rollback_to_restore_point(service: UpdateService) -> None:
    await service.run_update(UpdateChannel.STABLE)
    points = service.list_restore_points()
    assert points

    report = await service.rollback_to(points[0].id)
    assert report.succeeded is True


@pytest.mark.asyncio
async def test_voice_announcements_fire_during_update(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path)
    voice = VoiceAnnouncementService(settings)
    service = UpdateService(settings, voice_announcer=voice)

    await service.run_update(UpdateChannel.STABLE)

    assert any("Downloading" in line for line in voice.history)
    assert any("completed" in line.lower() for line in voice.history)
