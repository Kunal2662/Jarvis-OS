"""Unit tests for :meth:`SystemService.status` (Milestone 5-Agents)."""

from __future__ import annotations

import builtins

import pytest

from jarvis.core.config.settings import Settings
from jarvis.services.system_service import SystemService


@pytest.mark.asyncio
async def test_status_degrades_gracefully_without_psutil(monkeypatch) -> None:
    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("simulated: psutil not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)

    service = SystemService(Settings())
    result = await service.status()

    assert result == {"available": False}


@pytest.mark.asyncio
async def test_status_reports_live_metrics_when_psutil_available() -> None:
    pytest.importorskip("psutil")

    service = SystemService(Settings())
    result = await service.status()

    assert result["available"] is True
    for key in (
        "cpu_percent",
        "cpu_count",
        "memory_percent",
        "memory_total_mb",
        "disk_percent",
        "process_count",
        "uptime_seconds",
    ):
        assert key in result
    assert result["process_count"] > 0
