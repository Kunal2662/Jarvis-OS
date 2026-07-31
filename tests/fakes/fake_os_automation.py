"""Deterministic in-memory fake for :class:`IOSAutomation`."""

from __future__ import annotations

from jarvis.core.interfaces.automation import IOSAutomation, WindowInfo


class FakeOSAutomation(IOSAutomation):
    name: str = "fake"
    supported: bool = False  # forces actions to fall back to platform_ops in tests

    def __init__(self) -> None:
        self.launched: list[str] = []

    async def list_windows(self) -> list[WindowInfo]:
        return []

    async def focus_window(self, handle: int) -> None:
        return None

    async def launch(self, executable: str, args: list[str] | None = None) -> int:
        self.launched.append(executable)
        return 1234

    async def send_text(self, text: str) -> None:
        return None

    async def send_hotkey(self, combo: str) -> None:
        return None

    async def screenshot(self, output_path: str) -> str:
        return output_path
