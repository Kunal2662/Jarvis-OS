"""Windows OS-automation adapter using *pywinauto*.

This module is only imported when running on Windows -- see
:func:`jarvis.core.di.container._build_os_automation`. ``pywinauto`` is
imported lazily inside each method (not at module scope) so this file can
still be *imported* (for type-checking / tests) on non-Windows hosts; only
*calling* a method off-Windows raises.
"""

from __future__ import annotations

import asyncio
import subprocess
from typing import TYPE_CHECKING

from jarvis.core.exceptions import OSAutomationError
from jarvis.core.interfaces.automation import IOSAutomation, WindowInfo
from jarvis.infrastructure.automation.platform_ops import WindowsOps

if TYPE_CHECKING:
    from jarvis.core.config.settings import WindowsAutomationSettings


class WindowsAutomationAdapter(IOSAutomation):
    name: str = "pywinauto"
    supported: bool = True

    def __init__(self, settings: WindowsAutomationSettings) -> None:
        self._settings = settings
        self._ops = WindowsOps()

    def _desktop(self):
        try:
            from pywinauto import Desktop
        except ImportError as err:
            raise OSAutomationError(
                "pywinauto is not installed; OS-level window automation is unavailable."
            ) from err
        return Desktop(backend=self._settings.backend)

    async def list_windows(self) -> list[WindowInfo]:
        def _list() -> list[WindowInfo]:
            desktop = self._desktop()
            out: list[WindowInfo] = []
            for w in desktop.windows():
                try:
                    out.append(
                        WindowInfo(
                            handle=w.handle,
                            title=w.window_text(),
                            process_id=w.process_id(),
                            class_name=w.class_name(),
                        )
                    )
                except Exception:
                    continue
            return out

        return await asyncio.to_thread(_list)

    async def focus_window(self, handle: int) -> None:
        def _focus() -> None:
            from pywinauto import Application

            Application(backend=self._settings.backend).connect(
                handle=handle
            ).top_window().set_focus()

        await asyncio.to_thread(_focus)

    async def launch(self, executable: str, args: list[str] | None = None) -> int:
        def _launch() -> int:
            proc = subprocess.Popen([executable, *(args or [])])
            return proc.pid

        return await asyncio.to_thread(_launch)

    async def send_text(self, text: str) -> None:
        def _send() -> None:
            from pywinauto.keyboard import send_keys

            send_keys(text, with_spaces=True)

        await asyncio.to_thread(_send)

    async def send_hotkey(self, combo: str) -> None:
        def _send() -> None:
            from pywinauto.keyboard import send_keys

            # pywinauto hotkey syntax: "ctrl+alt+j" -> "^%j"
            mapping = {"ctrl": "^", "alt": "%", "shift": "+"}
            parts = combo.lower().split("+")
            *mods, key = parts
            prefix = "".join(mapping.get(m, "") for m in mods)
            send_keys(f"{prefix}{key}")

        await asyncio.to_thread(_send)

    async def screenshot(self, output_path: str) -> str:
        return await asyncio.to_thread(self._ops.screenshot, output_path)
