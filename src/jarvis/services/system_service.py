"""System service — process / battery / network diagnostics via psutil.

Was a ``NotImplementedError`` stub since Milestone 1. Milestone 5's
System Information and Performance Monitor developer views independently
call ``psutil`` themselves rather than going through this service (see
``docs/MASTER_ROADMAP.md`` §10, "orphaned" stub note); this fills the stub
in for real, without touching either view, so that Milestone 5-Agents can
expose it as the agent's ``get_system_status`` tool. Those two views are
left as-is (out of scope for this milestone; tracked separately as a
follow-up de-duplication candidate).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

_logger = get_logger("jarvis.services.system")


class SystemService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def status(self) -> dict[str, object]:
        """Snapshot of host CPU/memory/disk/uptime/process counts.

        Never raises: if ``psutil`` is unavailable (not installed, or a
        sandboxed environment that blocks it), returns a payload with
        ``"available": False`` rather than failing the caller — matching
        every other best-effort read path in this codebase (e.g.
        ``MemoryService.recall``).
        """
        try:
            import psutil
        except ImportError:
            _logger.warning("psutil not available; returning degraded system status.")
            return {"available": False}

        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage(str(self._settings.resolved_data_dir.anchor or "/"))
            boot_time = psutil.boot_time()
            uptime_seconds = max(0.0, time.time() - boot_time)
            return {
                "available": True,
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(logical=True) or 0,
                "memory_percent": mem.percent,
                "memory_total_mb": round(mem.total / (1024 * 1024), 1),
                "memory_used_mb": round(mem.used / (1024 * 1024), 1),
                "disk_percent": disk.percent,
                "disk_total_gb": round(disk.total / (1024**3), 1),
                "disk_free_gb": round(disk.free / (1024**3), 1),
                "process_count": len(psutil.pids()),
                "uptime_seconds": round(uptime_seconds, 0),
            }
        except Exception as err:
            _logger.warning("System status collection failed: {}", err)
            return {"available": False, "error": str(err)}
