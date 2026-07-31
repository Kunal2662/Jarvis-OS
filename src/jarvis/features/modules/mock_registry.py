"""Module registry -- mock backend for the expanded Module Manager
(Milestone 5, section 6).

Reflects JARVIS's own internal subsystems (the same ones the original
``ModuleManagerView`` listed by reading real ``Settings`` flags) but
adds the richer shape the brief asks for -- version, dependencies,
enable/disable/reload/update actions -- as a mock in-memory registry,
since there's no real module-hot-reload machinery to back "Reload" or
"Update" with today. Enabled/Disabled *state* still starts from the
real settings flags where one exists (more honest than inventing
state), but every action here (enable/disable/reload/update) mutates
the mock registry, not the actual running subsystem.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings


@dataclass
class ModuleInfo:
    name: str
    version: str
    dependencies: list[str]
    enabled: bool
    description: str = ""
    status: str = "stopped"  # stopped | running | reloading | error

    def __post_init__(self) -> None:
        if self.status == "stopped" and self.enabled:
            self.status = "running"


class ModuleRegistryService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._modules: dict[str, ModuleInfo] = self._seed()

    def _seed(self) -> dict[str, ModuleInfo]:
        s = self._settings
        specs = [
            (
                "Automation Engine",
                "2.1.0",
                [],
                s.automation.enabled,
                "Executes natural-language desktop/browser automations.",
            ),
            (
                "Memory System",
                "1.4.2",
                ["Vector Store"],
                s.memory.enabled,
                "Long-term recall and memory policies.",
            ),
            ("Vector Store", "1.0.3", [], True, "Embedding storage backing Memory System."),
            ("Voice Pipeline (STT)", "1.2.0", [], s.stt.enabled, "Speech-to-text transcription."),
            ("Voice Pipeline (TTS)", "1.2.0", [], s.tts.enabled, "Text-to-speech synthesis."),
            (
                "Wake Word Detection",
                "0.9.1",
                ["Voice Pipeline (STT)"],
                s.wake.enabled,
                '"Hey Jarvis" wake-word listener.',
            ),
            (
                "Browser Automation",
                "1.1.0",
                [],
                s.browser.enabled,
                "Drives a real browser via natural-language commands.",
            ),
            (
                "Windows Desktop Automation",
                "1.0.5",
                [],
                s.win_automation.enabled,
                "OS-level UI automation.",
            ),
            (
                "Update Center",
                "1.0.0",
                [],
                True,
                "Checks, downloads, and installs application updates.",
            ),
            ("API Center", "1.0.0", [], True, "Manages third-party API credentials and health."),
        ]
        return {
            name: ModuleInfo(
                name=name, version=version, dependencies=deps, enabled=enabled, description=desc
            )
            for name, version, deps, enabled, desc in specs
        }

    def list_installed(self) -> list[ModuleInfo]:
        return [m for m in self._modules.values() if m.enabled]

    def list_disabled(self) -> list[ModuleInfo]:
        return [m for m in self._modules.values() if not m.enabled]

    def list_all(self) -> list[ModuleInfo]:
        return list(self._modules.values())

    async def enable(self, name: str) -> ModuleInfo:
        await asyncio.sleep(0.05)
        module = self._modules[name]
        module.enabled = True
        module.status = "running"
        return module

    async def disable(self, name: str) -> ModuleInfo:
        await asyncio.sleep(0.05)
        module = self._modules[name]
        module.enabled = False
        module.status = "stopped"
        return module

    async def reload(self, name: str) -> ModuleInfo:
        module = self._modules[name]
        module.status = "reloading"
        await asyncio.sleep(0.15)
        module.status = "running" if module.enabled else "stopped"
        return module

    async def check_update(self, name: str) -> dict:
        await asyncio.sleep(0.1)
        module = self._modules[name]
        has_update = random.random() < 0.3
        return {
            "module": name,
            "current_version": module.version,
            "latest_version": _bump(module.version) if has_update else module.version,
            "update_available": has_update,
        }


def _bump(version: str) -> str:
    parts = version.split(".")
    parts[-1] = str(int(parts[-1]) + 1)
    return ".".join(parts)
