"""Bundled-font loading -- the Qt-side counterpart to
:mod:`jarvis.ui.themes.typography`'s pure-data scale.

Kept behind a runtime import (mirrors
:mod:`jarvis.ui.themes.theme_manager`) so :mod:`jarvis.ui.themes` stays
importable in environments without PySide6.

Must run once, before any QSS referencing ``Typography.FONT_FAMILY`` is
applied to the ``QApplication`` -- otherwise "Inter" silently falls
through the QSS fallback stack to whatever's installed on the OS, since
Qt has no concept of a font family that will exist "later."
"""

from __future__ import annotations

from jarvis.core.config import paths
from jarvis.core.logging.logger import get_logger

_logger = get_logger("jarvis.ui.themes.fonts")

# Only the one variable font file this app actually ships -- covers every
# weight in Typography.FontWeight (400/500/600/700) via its own weight
# axis, so a single addApplicationFont call is enough; no separate
# static-weight files to keep in sync.
_BUNDLED_FONT_FILENAME = "Inter.ttf"


def load_application_fonts() -> bool:
    """Register every bundled font file with Qt. Returns ``True`` if the
    bundled font loaded successfully, ``False`` if it's missing or
    rejected by Qt -- callers should treat ``False`` as non-fatal (the
    QSS fallback stack still renders something), just log-worthy."""
    from PySide6.QtGui import QFontDatabase

    font_path = paths.FONTS_DIR / _BUNDLED_FONT_FILENAME
    if not font_path.is_file():
        _logger.warning("Bundled font not found at {} -- falling back to system fonts.", font_path)
        return False

    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id == -1:
        _logger.warning(
            "Qt rejected the bundled font at {} -- falling back to system fonts.", font_path
        )
        return False

    families = QFontDatabase.applicationFontFamilies(font_id)
    _logger.info("Loaded bundled font {} -> families: {}", font_path.name, families)
    return True
