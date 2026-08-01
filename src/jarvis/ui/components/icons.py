"""Central icon system (Milestone 5, section 3; SVG system built out in
the UI overhaul's Typography/Icon phase).

Every icon used anywhere in the official UI -- sidebar nav, service
cards, workspace headers, toolbars -- is looked up by a single semantic
key through :data:`icon_registry` instead of being hard-coded as a
literal emoji string at each call site. That means the whole app's
iconography can be swapped from one place with **zero** changes to any
view or component.

Three tiers are supported, resolved in this order:

1. **Custom SVG** -- a file at ``resources/icons/<key>.svg`` (drop a
   file in and it wins automatically, no code change). Vendored from
   Lucide (ISC license, ``resources/icons/LICENSE.txt``) -- only the
   set JARVIS actually uses, not the full library.
2. **Icon pack** -- a registered mapping (see
   :meth:`IconRegistry.register_pack`) for a future non-Lucide source.
3. **Emoji fallback** -- only reached if a key has no SVG file and no
   pack entry, which should never happen for a key this app actually
   ships an icon for. Kept as a safety net, not a rendering path any
   shipped screen should hit.

SVGs are Lucide's raw ``stroke="currentColor"`` files -- rendered via
:class:`QSvgRenderer` onto a :class:`QPixmap` with ``currentColor``
substituted for a real hex color at render time, so the *same* SVG file
renders correctly in every theme (dark/light/jarvis) and at any
requested size/DPI, without needing per-theme copies of every icon.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QObject, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

try:  # pragma: no cover - optional at runtime
    from PySide6.QtSvg import QSvgRenderer

    _HAS_SVG = True
except Exception:  # pragma: no cover
    _HAS_SVG = False

# Semantic key -> emoji fallback glyph. Never the primary rendering path
# once resources/icons/<key>.svg exists for a key (see module docstring)
# -- kept only so a key with no SVG file yet still shows *something*
# instead of a blank widget.
_EMOJI_DEFAULTS: dict[str, str] = {
    "home": "\U0001f3e0",
    "chat": "\U0001f4ac",
    "voice": "\U0001f399",
    "memory": "\U0001f9e0",
    "automations": "⚙",
    "files": "\U0001f4c1",
    "browser": "\U0001f310",
    "coding": "\U0001f5a5",
    "finance": "\U0001f4c8",
    "smart_home": "\U0001f3e1",
    "calendar": "\U0001f4c5",
    "gmail": "✉",
    "spotify": "\U0001f3b5",
    "settings": "⚙",
    "weather": "⛅",
    "search": "\U0001f50d",
    "refresh": "⟳",
    "add": "＋",
    "edit": "✎",
    "delete": "\U0001f5d1",
    "play": "▶",
    "pause": "⏸",
    "download": "⬇",
    "upload": "⬆",
    "check": "✓",
    "warning": "⚠",
    "error": "✗",
    "info": "ℹ",
    "lock": "\U0001f512",
    "unlock": "\U0001f513",
    "plugin": "\U0001f9e9",
    "module": "\U0001f4e6",
    "history": "\U0001f550",
    "notification": "\U0001f514",
    "connected": "●",
    "offline": "○",
    "task": "☑",
    "code": "</>",
    "terminal": "⌘",
    "dock_bottom": "⬒",
    "dock_left": "◧",
    "dock_right": "◨",
    "float": "▢",
    "fullscreen": "⛶",
    "star_filled": "★",
    "star_outline": "☆",
    "builtin_badge": "\U0001f527",
    "dashboard": "\U0001f4ca",
    "api_center": "\U0001f50c",
    "ai_models": "\U0001f916",
    "performance": "\U0001f4c8",
    "logs": "\U0001f4dc",
    "configuration": "⚙",
    "security": "\U0001f6e1",
    "backup": "\U0001f4be",
    "system_info": "\U0001f5a5",
    "agent_trace": "\U0001f9e0",
    "vision_status": "\U0001f441",
    "wind": "\U0001f4a8",
    "chart": "\U0001f4ca",
    "link": "\U0001f517",
    "screenshot": "\U0001f4f8",
    "calculator": "\U0001f9ee",
    "note": "\U0001f4dd",
    "commit": "✅",
    "merge": "\U0001f500",
    "bug": "\U0001f41b",
    "power_off": "⭕",
    "moon": "\U0001f319",
    "mute": "\U0001f507",
    "speaking": "\U0001f5e3",
    "timer": "⏱",
    "pin": "\U0001f4cc",
    "archive": "\U0001f5c4",
    "avatar": "\U0001f9d1",
    "device_light": "\U0001f4a1",
    "device_climate": "\U0001f321",
    "device_camera": "\U0001f4f7",
    "device_generic": "\U0001f50c",
}


class IconRegistry:
    """Resolves a semantic icon key to a displayable glyph or asset,
    trying custom SVG -> registered icon pack -> emoji fallback."""

    def __init__(self, icons_dir: Path | None = None) -> None:
        self._icons_dir = icons_dir
        self._emoji: dict[str, str] = dict(_EMOJI_DEFAULTS)
        self._pack: dict[str, str] = {}  # key -> pack glyph/name (e.g. lucide id)
        # Theme-driven, set once per ThemeManager.apply() call (see
        # jarvis.ui.themes.theme_manager) so every icon repaints in the
        # newly-active theme's colors without each call site needing to
        # know or care which theme is active.
        self._default_color = "#DFF6FF"
        self._hover_color = "#00E5FF"
        self._success_color = "#00E39A"
        self._danger_color = "#FF3860"
        self._warning_color = "#FFD166"
        self._svg_cache: dict[str, str] = {}

    def set_icons_dir(self, path: Path) -> None:
        self._icons_dir = path
        self._svg_cache.clear()

    def set_theme_colors(
        self,
        *,
        default: str,
        hover: str,
        success: str | None = None,
        danger: str | None = None,
        warning: str | None = None,
    ) -> None:
        """Called by ThemeManager.apply() with the active theme's
        Palette fields so every icon -- including status glyphs that
        carry meaning through color -- re-renders correctly on a theme
        switch."""
        self._default_color = default
        self._hover_color = hover
        if success is not None:
            self._success_color = success
        if danger is not None:
            self._danger_color = danger
        if warning is not None:
            self._warning_color = warning

    @property
    def default_color(self) -> str:
        return self._default_color

    @property
    def hover_color(self) -> str:
        return self._hover_color

    @property
    def success_color(self) -> str:
        return self._success_color

    @property
    def danger_color(self) -> str:
        return self._danger_color

    @property
    def warning_color(self) -> str:
        return self._warning_color

    def register(self, key: str, emoji: str) -> None:
        """Override or add a single icon's emoji fallback at runtime."""
        self._emoji[key] = emoji

    def register_pack(self, mapping: dict[str, str]) -> None:
        """Register a future icon pack (e.g. a second SVG source) keyed
        by the same semantic keys used everywhere else."""
        self._pack.update(mapping)

    def svg_path(self, key: str) -> Path | None:
        if self._icons_dir is None:
            return None
        candidate = self._icons_dir / f"{key}.svg"
        return candidate if candidate.is_file() else None

    def svg_template(self, key: str) -> str | None:
        """Raw SVG source for *key* (with ``currentColor`` still
        literal, not yet substituted), cached after first read."""
        if key in self._svg_cache:
            return self._svg_cache[key]
        path = self.svg_path(key)
        if path is None:
            return None
        text = path.read_text(encoding="utf-8")
        self._svg_cache[key] = text
        return text

    def glyph(self, key: str, default: str = "•") -> str:
        """The best available *text* representation of an icon -- the
        emoji-fallback tier's rendering, and what any legacy call site
        still concatenating a glyph into a QPushButton's text expects."""
        return self._pack.get(key) or self._emoji.get(key, default)

    def keys(self) -> list[str]:
        return sorted(set(self._emoji) | set(self._pack))

    def pixmap(
        self, key: str, *, size: int = 20, color: str | None = None, device_pixel_ratio: float = 1.0
    ) -> QPixmap | None:
        """Render *key*'s SVG at *size* logical pixels in *color*
        (defaults to the active theme's default icon color). Returns
        ``None`` if no SVG exists for *key* (caller should fall back to
        :meth:`glyph`) or PySide6's SVG module isn't available."""
        if not _HAS_SVG:
            return None
        template = self.svg_template(key)
        if template is None:
            return None

        resolved_color = color or self._default_color
        svg = template.replace("currentColor", resolved_color)
        renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        if not renderer.isValid():
            return None

        px_size = max(1, round(size * device_pixel_ratio))
        pixmap = QPixmap(px_size, px_size)
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return pixmap

    def qicon(self, key: str, *, size: int = 20) -> QIcon:
        """A :class:`QIcon` for *key*, suitable for
        ``QPushButton.setIcon`` / ``QAction.setIcon``. Falls back to an
        empty ``QIcon`` (Qt renders nothing, not a broken-image glyph)
        if no SVG exists for *key*."""
        pixmap = self.pixmap(key, size=size)
        if pixmap is None:
            return QIcon()
        return QIcon(pixmap)


# Module-level singleton -- every component imports this rather than
# constructing its own registry, so registering a custom pack (or a new
# theme's colors) once affects the whole UI immediately.
icon_registry = IconRegistry()


class Icon(QWidget):
    """Drop-in icon widget: renders the registry's SVG for ``key`` at
    ``size`` logical pixels, re-rendering on hover if the widget's
    ``hoverable`` flag is set (used for standalone, clickable icons;
    icons embedded in a QPushButton get hover styling from the button
    itself instead). Falls back to a glyph ``QLabel`` if no SVG exists
    for ``key``."""

    def __init__(
        self,
        key: str,
        *,
        size: int = 20,
        color: str | None = None,
        hoverable: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._key = key
        self._size = size
        self._color = color
        self._hoverable = hoverable
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(QSize(size, size))
        self._render(hovered=False)
        if hoverable:
            self.installEventFilter(self)

    def _dpr(self) -> float:
        window = self.window()
        return window.devicePixelRatioF() if window is not None else 1.0

    def set_key(self, key: str) -> None:
        """Swap which icon is shown -- for status glyphs that change at
        runtime (e.g. StepProgress's pending/running/succeeded/failed)."""
        self._key = key
        self._render(hovered=False)

    def set_color(self, color: str | None) -> None:
        """Override the render color (``None`` reverts to the active
        theme's default) -- for status glyphs that carry meaning through
        color (success green, failure red) independent of hover state."""
        self._color = color
        self._render(hovered=False)

    def _render(self, *, hovered: bool) -> None:
        color = self._color or (
            icon_registry.hover_color if hovered else icon_registry.default_color
        )
        pixmap = icon_registry.pixmap(
            self._key, size=self._size, color=color, device_pixel_ratio=self._dpr()
        )
        if pixmap is not None:
            self._label.setPixmap(pixmap)
            self._label.setFixedSize(QSize(self._size, self._size))
            return
        self._label.setText(icon_registry.glyph(self._key))
        font = self._label.font()
        font.setPointSize(max(8, int(self._size * 0.62)))
        self._label.setFont(font)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self and self._hoverable:
            if event.type() == QEvent.Type.Enter:
                self._render(hovered=True)
            elif event.type() == QEvent.Type.Leave:
                self._render(hovered=False)
        return super().eventFilter(watched, event)


def icon_or_literal(key_or_glyph: str, *, size: int = 16) -> QWidget:
    """An ``Icon`` if *key_or_glyph* is a registered icon_registry key,
    otherwise a plain glyph ``QLabel`` showing it verbatim.

    Several call sites render icon-ish strings from two different
    sources at once: this app's own UI code (always a semantic key once
    converted) and mock-provider fixture data (``features.integrations.
    mocks``, deliberately left as literal emoji -- see the Mock Data
    section of the UI overhaul brief). This picks the right rendering
    for either without the caller needing to know which it got."""
    if icon_registry.svg_path(key_or_glyph) is not None:
        return Icon(key_or_glyph, size=size)
    label = QLabel(key_or_glyph)
    label.setFixedWidth(size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return label
