"""Developer Mode settings page -- Milestone 5, section 10A.

A status summary plus the entry point into the full Developer Mode
shell. The heavyweight content (API Center, Update Center, ...) lives in
``jarvis.ui.views.developer``, not here -- this page is just a signpost
inside the regular Settings dialog for people who go looking for
Developer Mode there.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QPushButton

from jarvis.ui.dialogs.settings_pages.base import SettingsPage


class DeveloperModePage(SettingsPage):
    id = "developer_mode"
    title = "Developer Mode"
    category = "Developer"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel(
            "Developer Mode (Dashboard, API Center, Update Center, Module/Plugin "
            "managers, Performance Monitor, Logs, Configuration, Security Center, "
            "Backup & Restore, Console, System Information) is protected by its own "
            "administrator password. JARVIS itself never requires a password to launch."
        )
        subtitle.setWordWrap(True)
        subtitle.setProperty("role", "muted")
        self._layout.addWidget(subtitle)

        self._status = QLabel("")
        self._layout.addWidget(self._status)
        self._refresh_status()

        open_btn = QPushButton("Open Developer Mode…")
        open_btn.setProperty("variant", "primary")
        open_btn.clicked.connect(self._open)
        self._layout.addWidget(open_btn)
        self._layout.addStretch(1)

    def _refresh_status(self) -> None:
        configured = bool(self._settings.dev_mode.password_hash.get_secret_value())
        self._status.setText(
            "Status: password configured." if configured else "Status: no password set yet."
        )

    def _open(self) -> None:
        if self._container is None:
            return
        from jarvis.ui.views.developer.entry import open_developer_mode

        open_developer_mode(self._settings, self._container, self)
        self._refresh_status()
