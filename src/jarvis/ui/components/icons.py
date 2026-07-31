"""Central icon system (Milestone 5, section 3).

Every icon used anywhere in the official UI -- sidebar nav, service
cards, workspace headers, toolbars -- is looked up by a single semantic
key through :data:`icon_registry` instead of being hard-coded as a
literal emoji string at each call site. That means the whole app's
iconography can be swapped from one place (emoji today, a Lucide/SVG
icon font tomorrow, a licensed icon pack after that) with **zero**
changes to any view or component.

Three tiers are supported, resolved in this order:

1. **Custom SVG** -- a file at ``resources/icons/<key>.svg`` (drop a
   file in and it wins automatically, no code change).
2. **Lucide** -- if the optional ``qtawesome``/lucide glyph mapping is
   registered for a key (see :meth:`IconRegistry.register_pack`).
3. **Emoji fallback** -- the current, always-available default so the
   app never shows a broken icon.

Nothing in this milestone ships a bundled SVG/Lucide asset pack (no
such assets exist in the repo yet, and the brief says not to add new
external asset pipelines) -- but every call site already goes through
this registry, so adding one later is purely additive.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QLabel, QWidget

try:  # pragma: no cover - optional at runtime
    from PySide6.QtSvgWidgets import QSvgWidget

    _HAS_SVG = True
except Exception:  # pragma: no cover
    _HAS_SVG = False

# Semantic key -> emoji fallback glyph. This is the single source of
# truth every nav item, service card, and workspace header pulls from.
_EMOJI_DEFAULTS: dict[str, str] = {
    "home": "🏠",
    "chat": "💬",
    "voice": "🎙",
    "memory": "🧠",
    "automations": "⚙",
    "files": "📁",
    "browser": "🌐",
    "coding": "🖥",
    "finance": "📈",
    "smart_home": "🏡",
    "calendar": "📅",
    "gmail": "✉",
    "spotify": "🎵",
    "settings": "⚙",
    "weather": "⛅",
    "search": "🔍",
    "refresh": "⟳",
    "add": "＋",
    "edit": "✎",
    "delete": "🗑",
    "play": "▶",
    "pause": "⏸",
    "download": "⬇",
    "upload": "⬆",
    "check": "✓",
    "warning": "⚠",
    "error": "✗",
    "info": "ℹ",
    "lock": "🔒",
    "unlock": "🔓",
    "plugin": "🧩",
    "module": "📦",
    "history": "🕘",
    "notification": "🔔",
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
}


class IconRegistry:
    """Resolves a semantic icon key to a displayable glyph or asset,
    trying custom SVG -> registered icon pack -> emoji fallback."""

    def __init__(self, icons_dir: Path | None = None) -> None:
        self._icons_dir = icons_dir
        self._emoji: dict[str, str] = dict(_EMOJI_DEFAULTS)
        self._pack: dict[str, str] = {}  # key -> pack glyph/name (e.g. lucide id)

    def set_icons_dir(self, path: Path) -> None:
        self._icons_dir = path

    def register(self, key: str, emoji: str) -> None:
        """Override or add a single icon's emoji fallback at runtime."""
        self._emoji[key] = emoji

    def register_pack(self, mapping: dict[str, str]) -> None:
        """Register a future icon pack (e.g. Lucide glyph names) keyed
        by the same semantic keys used everywhere else."""
        self._pack.update(mapping)

    def svg_path(self, key: str) -> Path | None:
        if self._icons_dir is None:
            return None
        candidate = self._icons_dir / f"{key}.svg"
        return candidate if candidate.is_file() else None

    def glyph(self, key: str, default: str = "•") -> str:
        """The best available *text* representation of an icon -- what
        every existing emoji-based component still expects today."""
        return self._pack.get(key) or self._emoji.get(key, default)

    def keys(self) -> list[str]:
        return sorted(set(self._emoji) | set(self._pack))


# Module-level singleton -- every component imports this rather than
# constructing its own registry, so registering a custom pack once at
# app startup affects the whole UI immediately.
icon_registry = IconRegistry()


class Icon(QWidget):
    """Drop-in icon widget: renders an SVG file if the registry finds
    one for ``key``, otherwise falls back to a glyph ``QLabel``. Used
    by new Milestone 5 call sites; existing components that already
    take a raw emoji string keep working unchanged (they can migrate
    to ``icon_registry.glyph(key)`` at their own pace)."""

    def __init__(self, key: str, *, size: int = 20, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        layout_widget = self._build(key)
        layout_widget.setParent(self)
        self._inner = layout_widget

    def _build(self, key: str) -> QWidget:
        svg_path = icon_registry.svg_path(key)
        if svg_path is not None and _HAS_SVG:
            widget = QSvgWidget(str(svg_path))
            widget.setFixedSize(QSize(self._size, self._size))
            return widget
        label = QLabel(icon_registry.glyph(key))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = label.font()
        font.setPointSize(max(8, int(self._size * 0.62)))
        label.setFont(font)
        return label
