"""Cross-platform global hotkey listener backed by ``pynput``.

``pynput`` runs its own daemon thread; callbacks are marshalled back to the
asyncio loop that was current when :meth:`start` was called so they can
freely emit Qt signals.

The adapter is deliberately loop-aware: it stores a reference to the loop
at start-up and uses ``call_soon_threadsafe`` to schedule callbacks —
never call a hotkey callback synchronously from the pynput thread.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from jarvis.core.exceptions import InfrastructureError
from jarvis.core.interfaces.hotkey import HotkeyCallback, IHotkeyListener
from jarvis.core.logging.logger import get_logger
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from pynput.keyboard import GlobalHotKeys

_logger = get_logger("jarvis.infrastructure.hotkey.pynput")


class PynputHotkeyListener(IHotkeyListener):
    name: str = "pynput"

    def __init__(self) -> None:
        self._listener: GlobalHotKeys | None = None
        self._bindings: dict[str, HotkeyCallback] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._listener is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._restart_listener()
        _logger.info("Global hotkey listener started ({} bindings).", len(self._bindings))

    async def stop(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
            self._listener = None
        _logger.info("Global hotkey listener stopped.")

    def bind(self, combo: str, callback: HotkeyCallback) -> None:
        self._bindings[self._normalize(combo)] = callback
        if self._listener is not None:
            self._restart_listener()

    def unbind(self, combo: str) -> None:
        self._bindings.pop(self._normalize(combo), None)
        if self._listener is not None:
            self._restart_listener()

    def rebind(self, old: str, new: str, callback: HotkeyCallback) -> None:
        self.unbind(old)
        self.bind(new, callback)

    # ------------------------------------------------------------------
    def _restart_listener(self) -> None:
        try:
            from pynput.keyboard import GlobalHotKeys
        except ImportError as err:  # pragma: no cover
            raise InfrastructureError(
                "pynput not installed. Add `pynput` to requirements.txt."
            ) from err

        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception:
                pass
        pynput_map: dict[str, callable] = {
            self._to_pynput(combo): self._make_dispatch(combo, cb)
            for combo, cb in self._bindings.items()
        }
        self._listener = GlobalHotKeys(pynput_map)
        self._listener.start()

    def _make_dispatch(self, combo: str, callback: HotkeyCallback):
        def _dispatch() -> None:
            loop = self._loop
            if loop is None or loop.is_closed():
                return

            def _run() -> None:
                try:
                    result = callback()
                    if asyncio.iscoroutine(result):
                        fire_and_forget(result)
                except Exception:
                    _logger.exception("Hotkey callback for {} failed.", combo)

            loop.call_soon_threadsafe(_run)

        return _dispatch

    @staticmethod
    def _normalize(combo: str) -> str:
        return combo.strip().lower().replace(" ", "")

    @staticmethod
    def _to_pynput(combo: str) -> str:
        """Convert ``ctrl+alt+j`` → ``<ctrl>+<alt>+j`` (pynput format)."""
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        aliases = {
            "ctrl": "<ctrl>",
            "control": "<ctrl>",
            "alt": "<alt>",
            "shift": "<shift>",
            "cmd": "<cmd>",
            "meta": "<cmd>",
            "super": "<cmd>",
            "win": "<cmd>",
            "space": "<space>",
            "enter": "<enter>",
            "return": "<enter>",
            "esc": "<esc>",
            "escape": "<esc>",
            "tab": "<tab>",
        }
        return "+".join(aliases.get(p, p) for p in parts)
