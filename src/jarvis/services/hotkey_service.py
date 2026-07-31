"""Hotkey service — thin registry over :class:`IHotkeyListener`.

Semantic names (``ptt``, ``toggle_window``) decouple *what* the app wants
from *which combo* is currently bound; changing the combo in Settings only
requires a ``update()`` call — no widget rewiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.interfaces.hotkey import HotkeyCallback
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.core.interfaces.hotkey import IHotkeyListener

_logger = get_logger("jarvis.services.hotkey")


class HotkeyService:
    def __init__(self, listener: IHotkeyListener, settings: Settings) -> None:
        self._listener = listener
        self._settings = settings
        self._current: dict[str, str] = {}  # semantic → combo

    async def start(self) -> None:
        if not self._settings.hotkey.enabled:
            _logger.info("Global hotkeys disabled.")
            return
        await self._listener.start()

    async def stop(self) -> None:
        await self._listener.stop()

    def register(self, semantic: str, combo: str, callback: HotkeyCallback) -> None:
        """Register (or replace) a semantic hotkey."""
        combo = combo.strip()
        if not combo:
            return
        previous = self._current.get(semantic)
        if previous and previous == combo:
            self._listener.bind(combo, callback)  # rebind fresh callback
            return
        if previous:
            self._listener.unbind(previous)
        self._listener.bind(combo, callback)
        self._current[semantic] = combo
        _logger.info("Bound hotkey {}={}", semantic, combo)

    def unregister(self, semantic: str) -> None:
        combo = self._current.pop(semantic, None)
        if combo:
            self._listener.unbind(combo)

    def current_combo(self, semantic: str) -> str | None:
        return self._current.get(semantic)
