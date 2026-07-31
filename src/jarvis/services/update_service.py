"""Update Center service (Milestone 5, sections 10C/10D/10E).

Owns the mock update pipeline (Checking -> Downloading -> Installing ->
Verifying -> Optimizing -> Restart Required -> Completed), automatic
restore-point creation before every run, automatic rollback on simulated
failure, version history / release notes per channel, and phase events
for the sidebar indicator + Update Terminal + voice announcements.

Every I/O-looking step (download, install, verify, optimize) is a timed
``asyncio.sleep`` -- there is no real package to fetch -- but the restore
point / rollback plumbing underneath is real (see
:mod:`jarvis.features.updates.rollback_manager`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger
from jarvis.domain.updates.models import (
    ReleaseNote,
    UpdateChannel,
    UpdatePhase,
    UpdateSession,
)
from jarvis.features.updates.rollback_manager import RollbackManager

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus
    from jarvis.domain.updates.models import RestorePoint, RollbackReport
    from jarvis.services.voice_announcement_service import VoiceAnnouncementService

_logger = get_logger("jarvis.services.update")

# Mock release history, newest first, per channel.
_RELEASE_HISTORY: dict[UpdateChannel, list[ReleaseNote]] = {
    UpdateChannel.STABLE: [
        ReleaseNote(
            "1.0.0",
            UpdateChannel.STABLE,
            datetime(2026, 6, 1, tzinfo=UTC),
            ["Milestone 4 automation engine", "Stability and performance fixes"],
        ),
        ReleaseNote(
            "0.9.0",
            UpdateChannel.STABLE,
            datetime(2026, 3, 15, tzinfo=UTC),
            ["Semantic memory recall", "Improved wake-word accuracy"],
        ),
    ],
    UpdateChannel.BETA: [
        ReleaseNote(
            "1.1.0-beta.2",
            UpdateChannel.BETA,
            datetime(2026, 7, 10, tzinfo=UTC),
            ["Milestone 5 dashboard UI", "Developer Mode preview"],
        ),
    ],
    UpdateChannel.DEVELOPER: [
        ReleaseNote(
            "1.2.0-dev.5",
            UpdateChannel.DEVELOPER,
            datetime(2026, 7, 25, tzinfo=UTC),
            ["API Center", "Update Center", "Experimental plugin loader"],
        ),
    ],
    UpdateChannel.NIGHTLY: [
        ReleaseNote(
            "1.2.0-nightly.20260730",
            UpdateChannel.NIGHTLY,
            datetime(2026, 7, 30, tzinfo=UTC),
            ["Latest unreviewed changes -- may be unstable"],
        ),
    ],
}

_PHASE_SEQUENCE: list[tuple[UpdatePhase, int, float]] = [
    (UpdatePhase.CHECKING, 5, 0.15),
    (UpdatePhase.DOWNLOADING, 55, 0.5),
    (UpdatePhase.INSTALLING, 78, 0.35),
    (UpdatePhase.VERIFYING, 90, 0.2),
    (UpdatePhase.OPTIMIZING, 98, 0.2),
    (UpdatePhase.RESTART_REQUIRED, 100, 0.05),
]


class UpdateService:
    def __init__(
        self,
        settings: Settings,
        *,
        event_bus: EventBus | None = None,
        voice_announcer: VoiceAnnouncementService | None = None,
    ) -> None:
        self._settings = settings
        self._event_bus = event_bus
        self._voice = voice_announcer
        self._rollback = RollbackManager(settings.resolved_data_dir)
        self._current_version = settings.app_version
        self._last_session: UpdateSession | None = None
        self._session_history: list[UpdateSession] = []

    # ------------------------------------------------------------------
    # Version / release info
    # ------------------------------------------------------------------
    @property
    def current_version(self) -> str:
        return self._current_version

    @property
    def event_bus(self) -> EventBus | None:
        return self._event_bus

    def version_history(self, channel: UpdateChannel | None = None) -> list[ReleaseNote]:
        channel = channel or UpdateChannel(self._settings.update.channel)
        return list(_RELEASE_HISTORY.get(channel, []))

    def check_for_updates(self, channel: UpdateChannel | None = None) -> ReleaseNote | None:
        notes = self.version_history(channel)
        if not notes:
            return None
        latest = notes[0]
        return latest if latest.version != self._current_version else None

    @property
    def last_session(self) -> UpdateSession | None:
        return self._last_session

    # ------------------------------------------------------------------
    # Session history (Milestone 5, section 8 -- sidebar update history).
    # Purely additive: extends what Update Center already tracked
    # (``last_session``) with a running history the sidebar can surface
    # without needing the full Update Center UI open.
    # ------------------------------------------------------------------
    def session_history(self, limit: int = 20) -> list[UpdateSession]:
        return list(reversed(self._session_history[-limit:]))

    def last_successful_session(self) -> UpdateSession | None:
        for session in reversed(self._session_history):
            if session.succeeded:
                return session
        return None

    def last_failed_session(self) -> UpdateSession | None:
        for session in reversed(self._session_history):
            if session.succeeded is False:
                return session
        return None

    def last_rollback_report(self) -> RollbackReport | None:
        for session in reversed(self._session_history):
            if session.rollback_report is not None:
                return session.rollback_report
        return None

    def list_restore_points(self) -> list[RestorePoint]:
        return self._rollback.list_restore_points()

    def create_restore_point_now(self) -> RestorePoint:
        return self._rollback.create_restore_point(self._current_version)

    async def rollback_to(self, restore_point_id: str) -> RollbackReport:
        await self._emit(UpdatePhase.ROLLBACK_STARTED, 0, "Manual rollback requested.", "")
        report = self._rollback.restore(restore_point_id)
        await self._emit(
            UpdatePhase.ROLLBACK_COMPLETED,
            100,
            "Rollback finished." if report.succeeded else "Rollback failed.",
            "",
        )
        return report

    # ------------------------------------------------------------------
    # Update pipeline
    # ------------------------------------------------------------------
    async def run_update(
        self, channel: UpdateChannel | None = None, *, simulate_failure: bool = False
    ) -> UpdateSession:
        import asyncio

        channel = channel or UpdateChannel(self._settings.update.channel)
        latest = self.check_for_updates(channel)
        target_version = latest.version if latest else self._current_version

        session = UpdateSession(
            channel=channel,
            from_version=self._current_version,
            to_version=target_version,
        )
        self._last_session = session
        session.logs.append(f"Starting update on '{channel.value}' channel...")

        restore_point = None
        if self._settings.update.create_restore_point:
            restore_point = self._rollback.create_restore_point(self._current_version)
            session.restore_point_id = restore_point.id
            session.logs.append(f"Restore point {restore_point.id[:8]} created.")

        failed = False
        for phase, target_progress, delay in _PHASE_SEQUENCE:
            session.phase = phase
            message = f"{phase.value.replace('_', ' ').title()}..."
            await self._emit(phase, target_progress, message, session.id)
            session.logs.append(f"[{phase.value}] {message}")
            await asyncio.sleep(delay)
            session.progress_percent = target_progress

            # Simulate a failure partway through installing, if asked.
            if simulate_failure and phase is UpdatePhase.INSTALLING:
                failed = True
                break

        if failed:
            session.phase = UpdatePhase.FAILED
            session.logs.append("Update failed during installation.")
            await self._emit(
                UpdatePhase.FAILED, session.progress_percent, "Update failed.", session.id
            )

            if restore_point is not None:
                await self._emit(
                    UpdatePhase.ROLLBACK_STARTED, 0, "Starting automatic rollback...", session.id
                )
                report = self._rollback.restore(restore_point.id)
                session.rollback_report = report
                session.logs.append(
                    "Rollback " + ("succeeded." if report.succeeded else "FAILED: " + report.notes)
                )
                await self._emit(
                    UpdatePhase.ROLLBACK_COMPLETED,
                    100,
                    "Previous version restored." if report.succeeded else "Rollback failed.",
                    session.id,
                )
            session.succeeded = False
        else:
            session.phase = UpdatePhase.COMPLETED
            session.succeeded = True
            self._current_version = target_version
            session.logs.append(f"Update completed. Now running {target_version}.")
            await self._emit(
                UpdatePhase.COMPLETED, 100, "Update completed successfully.", session.id
            )

        session.finished_at = datetime.now(UTC)
        self._session_history.append(session)
        return session

    # ------------------------------------------------------------------
    async def _emit(self, phase: UpdatePhase, progress: int, message: str, session_id: str) -> None:
        if self._voice is not None:
            await self._voice.announce(phase)
        if self._event_bus is not None:
            from jarvis.core.events.events import UpdatePhaseEvent

            await self._event_bus.publish(
                UpdatePhaseEvent(
                    session_id=session_id,
                    phase=phase.value,
                    progress_percent=progress,
                    message=message,
                )
            )
