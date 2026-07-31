"""No-op OS-automation adapter used on non-Windows platforms.

The rest of the application can call ``os_automation.foo()`` unconditionally;
this adapter simply raises a well-typed :class:`OSAutomationError` for any
call, and reports ``supported = False`` in health checks.
"""

from __future__ import annotations

from jarvis.core.exceptions import OSAutomationError
from jarvis.core.interfaces.automation import IOSAutomation, WindowInfo


class NoopAutomationAdapter(IOSAutomation):
    name: str = "noop"
    supported: bool = False

    def _unsupported(self) -> OSAutomationError:
        return OSAutomationError("OS automation is only available on Windows.")

    async def list_windows(self) -> list[WindowInfo]:
        raise self._unsupported()

    async def focus_window(self, handle: int) -> None:
        raise self._unsupported()

    async def launch(self, executable: str, args: list[str] | None = None) -> int:
        raise self._unsupported()

    async def send_text(self, text: str) -> None:
        raise self._unsupported()

    async def send_hotkey(self, combo: str) -> None:
        raise self._unsupported()

    async def screenshot(self, output_path: str) -> str:
        raise self._unsupported()
