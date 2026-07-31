"""Runtime theme application for ``QApplication``.

Delegates QSS resolution to :class:`~jarvis.services.theme_service.ThemeService`
(pure Python) and only concerns itself with the Qt side effects:

* applying the stylesheet on ``QApplication``,
* switching the accent colour via ``QPalette``,
* emitting a ``theme_changed`` Qt signal.

Kept behind a runtime import so that :mod:`jarvis.ui.themes` stays importable
in environments without PySide6 (e.g. unit tests for services).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from jarvis.core.logging.logger import get_logger
from jarvis.core.types import ThemeName

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from jarvis.services.theme_service import ThemeService

_logger = get_logger("jarvis.ui.themes")


class ThemeManager:
    """Applies themes to a ``QApplication`` instance."""

    def __init__(self, theme_service: ThemeService) -> None:
        self._service = theme_service
        self._current: ThemeName | None = None

    def apply(self, app: QApplication, theme: ThemeName | None = None) -> ThemeName:
        """Load *theme* (or the currently-active one) and apply it to *app*."""
        active = theme or self._service.active()
        qss = self._service.load(active)
        app.setStyleSheet(qss)
        self._current = active
        _logger.info("Applied theme: {}", active.value)
        return active

    def current(self) -> ThemeName | None:
        return self._current
