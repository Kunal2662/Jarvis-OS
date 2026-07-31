"""Theme settings page (Milestone 5, section 10: completed Theme Engine).

Adds an accent-color picker on top of the original theme dropdown --
the ``ThemeService`` accent-override machinery already exists, this is
just the first real call site for it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton

from jarvis.core.types import ThemeName
from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class ThemePage(SettingsPage):
    id = "theme"
    title = "Theme"
    category = "General"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._combo = QComboBox()
        for t in ThemeName:
            self._combo.addItem(t.value, t)
        current_idx = self._combo.findData(self._settings.ui.theme)
        if current_idx >= 0:
            self._combo.setCurrentIndex(current_idx)
        self._combo.currentIndexChanged.connect(self._on_theme_change)
        form.addRow("Active theme", self._combo)

        self._layout.addLayout(form)

        accent_label = QLabel("Accent color")
        accent_label.setStyleSheet("font-size:13px; font-weight:600; margin-top:12px;")
        self._layout.addWidget(accent_label)

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(8)
        from jarvis.services.theme_service import ThemeService

        theme_service = ThemeService(self._settings)
        self._accent_buttons: dict[str, QPushButton] = {}
        for name, hex_value in theme_service.available_accents().items():
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(name.title())
            btn.setCheckable(True)
            btn.setStyleSheet(
                f"QPushButton {{ background-color: {hex_value}; border-radius: 14px; "
                f"border: 2px solid transparent; }}"
                f"QPushButton:checked {{ border: 2px solid white; }}"
            )
            btn.setChecked(self._settings.ui.accent.lower() == hex_value.lower())
            btn.clicked.connect(lambda _c=False, n=name: self._on_accent_change(n))
            swatch_row.addWidget(btn)
            self._accent_buttons[name] = btn
        swatch_row.addStretch(1)
        self._layout.addLayout(swatch_row)

        self._layout.addStretch(1)

    def _on_theme_change(self) -> None:
        theme: ThemeName = self._combo.currentData()
        self._settings.ui.theme = theme
        self._theme_manager.apply(QApplication.instance(), theme)
        fire_and_forget(self._service.set_env("JARVIS_UI_THEME", theme.value))

    def _on_accent_change(self, accent_name: str) -> None:
        from jarvis.services.theme_service import ThemeService

        theme_service = ThemeService(self._settings)
        theme_service.set_accent(accent_name)
        for name, btn in self._accent_buttons.items():
            btn.setChecked(name == accent_name)
        self._theme_manager.apply(QApplication.instance(), self._settings.ui.theme)
        fire_and_forget(self._service.set_env("JARVIS_UI_ACCENT", self._settings.ui.accent))
