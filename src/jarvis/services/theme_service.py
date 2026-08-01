"""Theme service -- resolves and loads the active QSS theme (Milestone
5, section 10: completed Theme Engine).

Reads the raw QSS from ``resources/themes/<name>.qss`` and exposes it
as a string so the UI layer can inject it into
``QApplication.setStyleSheet``. Deliberately UI-framework-agnostic
(returns a ``str``) so it can be unit-tested without importing PySide6.

Completed in this pass:

* **``switch()``** -- was a ``NotImplementedError`` stub inherited from
  Milestone 1; now actually switches the in-memory active theme. Disk
  persistence continues to go through ``SettingsService.set_env`` (see
  ``ui/dialogs/settings_pages/theme_page.py``), since ``Settings``
  itself intentionally owns no file I/O -- ``switch()`` is the missing
  in-memory half, not a duplicate of that.
* **Accent colors** -- ``settings.ui.accent`` already existed as a
  field but was dead (``load()`` ignored it). ``load()`` now applies it
  as a safe, literal find-and-replace of the theme's default accent hex
  wherever it appears in the QSS, so the default UI is pixel-identical
  when the accent is left at its default (the common case today) and
  fully recolored when a user picks a different one.
* **Design tokens** -- ``tokens()`` exposes the theme's typography /
  spacing / border-radius / animation / blur / glow values as
  structured data (read from the same constants the QSS uses) for any
  future tool that wants to stay visually consistent without parsing
  QSS.
* **Future custom themes** -- ``list_custom_themes()`` / ``load_custom()``
  pick up any ``.qss`` dropped into ``resources/themes/custom/``,
  without touching the strict ``ThemeName`` enum that ``Settings.ui.theme``
  is validated against (custom themes are opt-in and orthogonal to the
  three built-in ones).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from jarvis.core.config import paths
from jarvis.core.exceptions import ThemeNotFoundError
from jarvis.core.types import ThemeName
from jarvis.ui.themes.palette import DARK_PALETTE, JARVIS_PALETTE, LIGHT_PALETTE
from jarvis.ui.themes.typography import Typography

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

# Each theme's default accent, read from palette.py's Palette objects
# (the single source of truth THEMING.md always documented -- audit fix:
# this used to be a separately hardcoded dict that happened to duplicate
# the same values, an accidental "duplicate implementation" introduced
# while completing the Theme Engine without noticing palette.py already
# existed for exactly this).
_DEFAULT_ACCENTS: dict[ThemeName, str] = {
    ThemeName.JARVIS: JARVIS_PALETTE.accent,
    ThemeName.DARK: DARK_PALETTE.accent,
    ThemeName.LIGHT: LIGHT_PALETTE.accent,
}

ACCENT_PALETTE: dict[str, str] = {
    "cyan": "#00E5FF",
    "blue": "#4C8DFF",
    "indigo": "#6366F1",
    "purple": "#A855F7",
    "green": "#3DDC97",
    "amber": "#F5A524",
    "rose": "#FB7185",
}

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")

# The out-of-the-box value of UISettings.accent -- used to detect "user
# never touched this setting" so switching themes while the accent is
# still at its factory default shows each theme's own native color
# instead of forcing an override onto it.
_FACTORY_DEFAULT_ACCENT = JARVIS_PALETTE.accent


@dataclass(frozen=True, slots=True)
class ThemeTokens:
    """Structured design tokens for the active theme (Milestone 5,
    section 10). Read-only metadata about typography/spacing/etc.;
    QSS remains the actual source of truth for rendering."""

    accent: str
    font_family: str = Typography.FONT_FAMILY_STACK
    base_font_size_px: int = Typography.SECONDARY.size_px
    spacing_unit_px: int = 8
    border_radius_px: int = 10
    animation_duration_ms: int = 180
    blur_radius_px: int = 24
    glow_color: str = ""

    def __post_init__(self) -> None:
        if not self.glow_color:
            object.__setattr__(self, "glow_color", self.accent)


class ThemeService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------
    # Built-in themes
    # ------------------------------------------------------------------
    def available(self) -> list[ThemeName]:
        return list(ThemeName)

    def active(self) -> ThemeName:
        return self._settings.ui.theme

    def load(self, name: ThemeName | None = None) -> str:
        """Return the QSS string for *name* (defaults to the active
        theme), with the active accent color applied on top."""
        theme = name or self.active()
        qss_path = paths.THEMES_DIR / f"{theme.value}.qss"
        if not qss_path.is_file():
            raise ThemeNotFoundError(f"Theme file not found: {qss_path}")
        qss = qss_path.read_text(encoding="utf-8")
        return self._apply_accent(qss, theme)

    def switch(self, name: ThemeName) -> None:
        """Switch the active theme in-memory. (Disk persistence is
        ``SettingsService.set_env("JARVIS_UI_THEME", ...)``'s job --
        see ``ui/dialogs/settings_pages/theme_page.py``.)"""
        self._settings.ui.theme = name

    # ------------------------------------------------------------------
    # Accent colors
    # ------------------------------------------------------------------
    def available_accents(self) -> dict[str, str]:
        return dict(ACCENT_PALETTE)

    def active_accent(self) -> str:
        return self._settings.ui.accent

    def set_accent(self, color: str) -> None:
        """Switch the active accent color in-memory. *color* may be a
        palette name (``"purple"``) or a literal ``#rrggbb`` hex."""
        resolved = ACCENT_PALETTE.get(color, color)
        if not _HEX_COLOR_RE.match(resolved):
            raise ValueError(f"Invalid accent color: {color!r}")
        self._settings.ui.accent = resolved

    def _apply_accent(self, qss: str, theme: ThemeName) -> str:
        default_accent = _DEFAULT_ACCENTS.get(theme)
        custom_accent = self._settings.ui.accent
        if not default_accent or not custom_accent:
            return qss
        if custom_accent.lower() == _FACTORY_DEFAULT_ACCENT.lower():
            return qss  # Never customized -- every theme shows its own native accent.
        if custom_accent.lower() == default_accent.lower():
            return qss  # No-op -- already matches this theme's accent.
        return re.sub(re.escape(default_accent), custom_accent, qss, flags=re.IGNORECASE)

    # ------------------------------------------------------------------
    # Design tokens (Milestone 5, section 10)
    # ------------------------------------------------------------------
    def tokens(self, name: ThemeName | None = None) -> ThemeTokens:
        theme = name or self.active()
        accent = (
            self._settings.ui.accent
            if theme == self.active()
            else _DEFAULT_ACCENTS.get(theme, "#00E5FF")
        )
        return ThemeTokens(accent=accent)

    # ------------------------------------------------------------------
    # Future custom themes -- drop a .qss into resources/themes/custom/
    # ------------------------------------------------------------------
    def custom_themes_dir(self) -> Path:
        """User-writable location for future custom themes -- lives
        under the data dir (not the app's installed ``resources/``
        folder, which may not be writable once packaged)."""
        path = self._settings.resolved_data_dir / "themes" / "custom"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def list_custom_themes(self) -> list[str]:
        return sorted(p.stem for p in self.custom_themes_dir().glob("*.qss"))

    def load_custom(self, name: str) -> str:
        qss_path = self.custom_themes_dir() / f"{name}.qss"
        if not qss_path.is_file():
            raise ThemeNotFoundError(f"Custom theme file not found: {qss_path}")
        return qss_path.read_text(encoding="utf-8")
