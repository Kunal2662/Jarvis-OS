"""OS-automation port.

The Windows adapter (``pywinauto``) implements the full interface; on other
platforms a NO-OP adapter is injected so the rest of the app remains
runnable and testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class WindowInfo:
    handle: int
    title: str
    process_id: int
    class_name: str = ""


@runtime_checkable
class IOSAutomation(Protocol):
    """Abstract OS-level automation (windows, keyboard, mouse, processes)."""

    name: str
    supported: bool

    async def list_windows(self) -> list[WindowInfo]: ...

    async def focus_window(self, handle: int) -> None: ...

    async def launch(self, executable: str, args: list[str] | None = None) -> int: ...

    async def send_text(self, text: str) -> None: ...

    async def send_hotkey(self, combo: str) -> None: ...

    async def screenshot(self, output_path: str) -> str: ...
