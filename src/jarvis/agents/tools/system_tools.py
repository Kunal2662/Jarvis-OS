"""Agent tools wrapping :class:`~jarvis.services.system_service.SystemService`."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from langchain_core.tools import BaseTool, tool

if TYPE_CHECKING:
    from jarvis.services.system_service import SystemService


def build_system_tools(system: SystemService) -> list[BaseTool]:
    @tool
    async def get_system_status() -> str:
        """Get the host machine's current CPU, memory, disk usage, process
        count, and uptime."""
        status = await system.status()
        if not status.get("available", False):
            return "System status unavailable (psutil not installed)."
        return (
            f"CPU: {status['cpu_percent']}% ({status['cpu_count']} cores), "
            f"Memory: {status['memory_percent']}% "
            f"({status['memory_used_mb']}/{status['memory_total_mb']} MB), "
            f"Disk: {status['disk_percent']}% used "
            f"({status['disk_free_gb']} GB free), "
            f"Processes: {status['process_count']}, "
            f"Uptime: {int(cast(float, status['uptime_seconds']) // 3600)}h"
        )

    return [get_system_status]
