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
from jarvis.ui.themes.palette import DARK_PALETTE, JARVIS_PALETTE, LIGHT_PALETTE

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

    from jarvis.services.theme_service import ThemeService

_logger = get_logger("jarvis.ui.themes")

_PALETTES = {
    ThemeName.JARVIS: JARVIS_PALETTE,
    ThemeName.DARK: DARK_PALETTE,
    ThemeName.LIGHT: LIGHT_PALETTE,
}


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
        self._apply_icon_colors(active)
        _logger.info("Applied theme: {}", active.value)
        return active

    def _apply_icon_colors(self, theme: ThemeName) -> None:
        """Every SVG icon re-renders in the newly-active theme's colors
        -- see IconRegistry.set_theme_colors()'s docstring for why this
        is one centralized call rather than threading the palette
        through every Icon(...) call site."""
        from jarvis.ui.components.icons import icon_registry

        palette = _PALETTES.get(theme, JARVIS_PALETTE)
        icon_registry.set_theme_colors(
            default=palette.text,
            hover=palette.accent,
            success=palette.success,
            danger=palette.danger,
            warning=palette.warning,
        )

    def current(self) -> ThemeName | None:
        return self._current
