"""Base class + registry for every Settings page.

Any file inside ``settings_pages/`` that exports a ``SettingsPage``
subclass and appends it to :data:`PAGE_REGISTRY` will automatically show
up in the Settings dialog — no wiring changes needed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QVBoxLayout, QWidget

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.settings_service import SettingsService
    from jarvis.ui.themes.theme_manager import ThemeManager


class SettingsPage(QWidget):
    """Base class for all Settings pages.

    Subclasses must set the ``id``, ``title`` and ``category`` class
    attributes, and override :meth:`build`.
    """

    id: str = ""
    title: str = ""
    category: str = ""

    def __init__(
        self,
        settings: Settings,
        settings_service: SettingsService,
        theme_manager: ThemeManager,
        parent: QWidget | None = None,
        *,
        memory_service: object | None = None,
        container: object | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._service = settings_service
        self._theme_manager = theme_manager
        # Optional — only pages that need it (e.g. MemoryPage) use this.
        self._memory_service = memory_service
        # Optional — Milestone 5 pages (Developer Mode) use this to reach
        # other DI-provided services without every page needing its own
        # bespoke constructor signature.
        self._container = container

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(12)
        self._layout: QVBoxLayout = outer
        self.build()

    def build(self) -> None:  # pragma: no cover — abstract
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PageDescriptor:
    id: str
    title: str
    category: str
    factory: Callable[..., SettingsPage]
    implemented: bool = True
    milestone: str = ""  # e.g. "Milestone 2 — Voice"


PAGE_REGISTRY: list[PageDescriptor] = []


# Order in which categories appear in the sidebar.
CATEGORY_ORDER: list[str] = [
    "General",
    "AI",
    "Voice",
    "Memory",
    "Vision",
    "Automation",
    "Plugins",
    "Smart Home",
    "Security",
    "Developer",
]


def register(descriptor: PageDescriptor) -> None:
    """Public entry point used by page modules to register themselves."""
    PAGE_REGISTRY.append(descriptor)


# ---------------------------------------------------------------------------
# Placeholder factory for future-milestone pages
# ---------------------------------------------------------------------------
class PlaceholderPage(SettingsPage):
    """Renders "Coming in <milestone>" text for not-yet-implemented pages."""

    _milestone: str = ""

    def build(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QLabel

        self.setObjectName(f"settingsPage-{self.id}")

        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(self._milestone or "Coming in a future milestone.")
        subtitle.setProperty("role", "muted")
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        body = QLabel(
            "The full settings architecture is already wired up — the UI you "
            "see here is a placeholder. When the underlying feature ships, "
            "this page will become editable without any changes to the "
            "surrounding dialog."
        )
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignmentFlag.AlignTop)
        body.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(body)
        self._layout.addStretch(1)


def make_placeholder(page_id: str, title: str, category: str, milestone: str) -> PageDescriptor:
    """Convenience helper to declare a placeholder page in one line."""
    factory_cls = type(
        f"PlaceholderPage_{page_id}",
        (PlaceholderPage,),
        {
            "id": page_id,
            "title": title,
            "category": category,
            "_milestone": milestone,
        },
    )
    return PageDescriptor(
        id=page_id,
        title=title,
        category=category,
        factory=factory_cls,
        implemented=False,
        milestone=milestone,
    )
