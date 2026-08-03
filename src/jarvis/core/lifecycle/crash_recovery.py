"""``CrashRecoveryManager`` -- process-level crash detection (Milestone
9 Task Group C, Reliability module). Extends ``RuntimeManager``'s
existing cleanup-on-exit guarantee (every registered shutdown hook
always runs, fault-isolated) with a real signal for the one case
shutdown hooks structurally cannot cover: the process never got to run
them at all (a hard crash, a killed process, a power loss).

**What "restart-on-crash" means here, concretely.** A process cannot
reliably restart itself after crashing -- by definition, if it
crashed, its own code stopped running. Automatically respawning a
fresh OS process after a crash needs an external supervisor/watchdog
process outside this application's own control -- real, separate,
future work, not something this class can honestly claim to do (see
``MASTER_ROADMAP.md``'s changelog addendum, Future Work).

What this class does today: writes a small on-disk marker
(``runtime_state.json``, via the existing ``core/config/paths.
config_dir`` convention every other JSON-config-store service already
uses, e.g. ``ApiCenterService``) at startup, before anything else
runs, and clears it only once shutdown has genuinely completed -- the
standard "mark dirty at start, mark clean at end" pattern. If the
marker is still dirty at the *next* startup, the previous run never
reached a clean shutdown. Detected here, published as
``CrashRecoveredEvent``, and left for other managers to act on in
their own domain (``SessionManager`` already does its own,
independent dangling-session recovery) rather than this class trying
to own every subsystem's own recovery logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from jarvis.core.config import paths as _paths
from jarvis.core.events.events import CrashRecoveredEvent
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from jarvis.core.config.settings import Settings
    from jarvis.core.events.event_bus import EventBus

_logger = get_logger("jarvis.core.lifecycle.crash_recovery")

_MARKER_FILENAME = "runtime_state.json"


@dataclass(frozen=True, slots=True)
class CrashRecoveryStatus:
    recovered_from_crash: bool
    previous_boot_at: str | None


class CrashRecoveryManager:
    def __init__(self, settings: Settings, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._marker_path: Path = _paths.config_dir(settings.resolved_data_dir) / _MARKER_FILENAME
        self._boot_at = ""
        self._status = CrashRecoveryStatus(recovered_from_crash=False, previous_boot_at=None)

    async def check_and_mark_dirty(self) -> CrashRecoveryStatus:
        """Call once, early in startup. Reads any marker the previous
        run left, then overwrites it with this run's own dirty marker.
        Never raises -- a missing, corrupt, or unreadable marker file
        is treated the same as "no marker", not a fatal error."""
        previous_boot_at: str | None = None
        recovered = False
        if self._marker_path.exists():
            try:
                raw = json.loads(self._marker_path.read_text(encoding="utf-8"))
                if raw.get("clean") is False:
                    recovered = True
                    previous_boot_at = raw.get("boot_at")
            except (OSError, ValueError) as err:
                _logger.warning("Could not read crash-recovery marker: {}", err)

        self._status = CrashRecoveryStatus(
            recovered_from_crash=recovered, previous_boot_at=previous_boot_at
        )

        if recovered:
            _logger.warning(
                "Recovered from an unclean shutdown -- the previous run (started {}) "
                "never marked itself clean.",
                previous_boot_at,
            )
            await self._event_bus.publish(
                CrashRecoveredEvent(previous_boot_at=previous_boot_at or "")
            )

        self._boot_at = datetime.now(UTC).isoformat()
        self._safe_write_marker(clean=False)
        return self._status

    def mark_clean(self) -> None:
        """Call once, at the very end of a graceful shutdown sequence
        -- after every other shutdown hook has actually run, so
        "clean" is accurate. Never raises; a failure to write the
        marker only means the next boot will (harmlessly) treat this
        run as a crash too."""
        self._safe_write_marker(clean=True)

    def _safe_write_marker(self, *, clean: bool) -> None:
        try:
            self._marker_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"clean": clean, "boot_at": self._boot_at}
            self._marker_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError as err:
            _logger.warning("Could not write crash-recovery marker: {}", err)

    @property
    def status(self) -> CrashRecoveryStatus:
        return self._status
