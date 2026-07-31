"""Global hotkey listener port.

The concrete adapter (``pynput``) runs a background thread that watches
the OS-level input queue; when a bound combo fires it calls the registered
callback on the asyncio loop that owns the app.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

HotkeyCallback = Callable[[], "Awaitable[None] | None"]


@runtime_checkable
class IHotkeyListener(Protocol):
    """Cross-platform global hotkey listener."""

    name: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    def bind(self, combo: str, callback: HotkeyCallback) -> None:
        """Register *callback* for *combo* (e.g. ``ctrl+alt+j``)."""

    def unbind(self, combo: str) -> None: ...

    def rebind(self, old: str, new: str, callback: HotkeyCallback) -> None:
        """Convenience: unbind ``old`` and bind ``new`` atomically."""
