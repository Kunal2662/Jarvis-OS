"""Typography design tokens -- the single source of truth for every font
size / weight used anywhere in the JARVIS UI.

Pure data, no PySide6 import (mirrors :mod:`jarvis.ui.themes.palette`) so
it stays importable in environments without Qt installed -- e.g. service
unit tests that only want the numeric scale, not a running application.
See :mod:`jarvis.ui.themes.fonts` for the Qt-side font-file loading this
scale depends on.

Every value here is drawn from one fixed scale; nothing outside this
module should declare a font size or weight of its own. QSS themes
(``resources/themes/*.qss``) hardcode the same numbers directly (QSS has
no variables), so if this scale ever changes, the QSS files must be
updated to match -- :func:`assert_qss_uses_only_scale_values` (in the
typography test suite) guards against the two drifting apart.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FontWeight(IntEnum):
    """The only four weights allowed anywhere in the JARVIS UI."""

    REGULAR = 400
    MEDIUM = 500
    SEMIBOLD = 600
    BOLD = 700


@dataclass(frozen=True, slots=True)
class TypeStyle:
    """One entry in the typography scale: a size/weight pair."""

    size_px: int
    weight: FontWeight


class Typography:
    """The complete typographic scale. Named after what the text *is*,
    not where it happens to be used, so the same token applies equally
    to a dashboard card title and a dialog title."""

    FONT_FAMILY = "Inter"
    # QSS fallback stack -- if "Inter" somehow isn't registered (e.g. the
    # bundled font file failed to load), degrade to the closest
    # system-available fonts rather than an unstyled default.
    FONT_FAMILY_STACK = '"Inter", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial", sans-serif'
    MONOSPACE_FAMILY_STACK = '"JetBrains Mono", "Cascadia Code", "Consolas", monospace'

    APP_TITLE = TypeStyle(32, FontWeight.BOLD)
    SECTION_TITLE = TypeStyle(24, FontWeight.BOLD)
    CARD_TITLE = TypeStyle(20, FontWeight.BOLD)
    WIDGET_TITLE = TypeStyle(18, FontWeight.SEMIBOLD)
    BODY = TypeStyle(16, FontWeight.REGULAR)
    SECONDARY = TypeStyle(14, FontWeight.REGULAR)
    CAPTION = TypeStyle(12, FontWeight.MEDIUM)

    @classmethod
    def scale(cls) -> dict[str, TypeStyle]:
        """Every named style in the scale, for tooling/tests that need
        to enumerate it rather than reference one member directly."""
        return {
            "app_title": cls.APP_TITLE,
            "section_title": cls.SECTION_TITLE,
            "card_title": cls.CARD_TITLE,
            "widget_title": cls.WIDGET_TITLE,
            "body": cls.BODY,
            "secondary": cls.SECONDARY,
            "caption": cls.CAPTION,
        }

    @classmethod
    def allowed_sizes_px(cls) -> frozenset[int]:
        return frozenset(style.size_px for style in cls.scale().values())

    @classmethod
    def allowed_weights(cls) -> frozenset[int]:
        return frozenset(int(w) for w in FontWeight)
