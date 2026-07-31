"""Qt-aware "fire and forget" wrapper around
``jarvis.utils.async_utils.fire_and_forget``.

The real app runs under ``qasync`` so there's always a running asyncio
loop by the time most widgets are constructed -- but a widget that
kicks off a background refresh from its own ``__init__`` (e.g.
``ServiceWidget``, the Milestone 5 workspaces) can occasionally race
the qasync loop's startup, in unit tests, or in a REPL, where
``asyncio.ensure_future()`` raises ``RuntimeError: There is no current
event loop``. This module adds exactly that one extra behaviour --
retry shortly via ``QTimer.singleShot`` instead of crashing widget
construction -- on top of the core helper's actual fix (a widget or
Qt slot handler that already knows a loop is running should just call
``jarvis.utils.async_utils.fire_and_forget`` directly).
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

from PySide6.QtCore import QTimer

from jarvis.utils.async_utils import fire_and_forget as _core_fire_and_forget


def fire_and_forget(coro: Coroutine[Any, Any, Any], *, retry_ms: int = 50) -> None:
    """Schedule ``coro`` on the running loop if one exists (with the
    core helper's anti-premature-GC protection); otherwise retry
    shortly via a Qt timer (covers the window between a widget being
    constructed and the app's event loop actually starting)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        QTimer.singleShot(retry_ms, lambda: fire_and_forget(coro, retry_ms=retry_ms))
        return
    _core_fire_and_forget(coro)
