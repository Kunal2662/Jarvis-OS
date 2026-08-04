"""Automation settings pages -- Milestone 4 (Automation Platform).

Both pages were `make_placeholder(...)` entries reading "Coming in
Milestone 4 — Automation" until the Aug 2026 final backlog pass. M4
shipped: `BrowserSettings` and `WindowsAutomationSettings` are real,
`BrowserService` and `AutomationService` consume them, and the
placeholder text had been wrong for several milestones. Nothing new is
built here -- these expose settings that already existed to the dialog
that already knew how to render them.

Two pages rather than one because the registry already declared two
ids (`browser`, `desktop_automation`) and the Settings sidebar groups
them under one "Automation" category either way; merging them would
have changed navigation for no benefit.
"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel

from jarvis.ui.dialogs.settings_pages.base import SettingsPage


class BrowserAutomationPage(SettingsPage):
    id = "browser"
    title = "Browser Automation"
    category = "Automation"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel("Drives a real browser from natural-language commands, via Playwright.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._enabled = QCheckBox("Enable browser automation")
        self._enabled.setChecked(self._settings.browser.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_BROWSER_ENABLED", "true" if v else "false", "browser.enabled", v
            )
        )
        form.addRow(self._enabled)

        self._engine = QComboBox()
        self._engine.addItems(["chromium", "firefox", "webkit"])
        self._engine.setCurrentText(self._settings.browser.engine)
        self._engine.currentTextChanged.connect(
            lambda v: self._persist("JARVIS_BROWSER_ENGINE", v, "browser.engine", v)
        )
        form.addRow("Engine", self._engine)

        self._headless = QCheckBox("Run headless (no visible browser window)")
        self._headless.setChecked(self._settings.browser.headless)
        self._headless.toggled.connect(
            lambda v: self._persist(
                "JARVIS_BROWSER_HEADLESS", "true" if v else "false", "browser.headless", v
            )
        )
        form.addRow(self._headless)

        self._layout.addLayout(form)

        # Read-only: this is a path the adapter manages, and letting a
        # user retarget it from here would strand the existing profile.
        profile = QLabel(f"Profile directory: {self._settings.browser.user_data_dir}")
        profile.setWordWrap(True)
        profile.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(profile)

        restart_note = QLabel(
            "Engine and headless changes apply the next time the browser is launched."
        )
        restart_note.setWordWrap(True)
        restart_note.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(restart_note)

        self._layout.addStretch(1)

    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value: object) -> None:
        _persist_setting(self, env_key, env_value, attr_path, live_value)


class DesktopAutomationPage(SettingsPage):
    id = "desktop_automation"
    title = "Desktop Automation"
    category = "Automation"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        subtitle = QLabel("OS-level UI automation — clicking, typing, and window control.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(subtitle)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._enabled = QCheckBox("Enable desktop automation")
        self._enabled.setChecked(self._settings.win_automation.enabled)
        self._enabled.toggled.connect(
            lambda v: self._persist(
                "JARVIS_WIN_AUTOMATION_ENABLED",
                "true" if v else "false",
                "win_automation.enabled",
                v,
            )
        )
        form.addRow(self._enabled)

        self._backend = QComboBox()
        self._backend.addItems(["uia", "win32"])
        self._backend.setCurrentText(self._settings.win_automation.backend)
        self._backend.currentTextChanged.connect(
            lambda v: self._persist("JARVIS_WIN_AUTOMATION_BACKEND", v, "win_automation.backend", v)
        )
        form.addRow("Backend", self._backend)

        self._layout.addLayout(form)

        if not sys.platform.startswith("win"):
            # Said plainly rather than by hiding the controls: the
            # settings are real and persist, they just have no adapter
            # to drive on this OS (`NoopAutomationAdapter`).
            unsupported = QLabel(
                "This platform has no desktop-automation adapter — these settings persist "
                "but nothing acts on them until JARVIS runs on Windows."
            )
            unsupported.setWordWrap(True)
            unsupported.setStyleSheet("color:#6D8BAA;")
            self._layout.addWidget(unsupported)

        self._layout.addStretch(1)

    def _persist(self, env_key: str, env_value: str, attr_path: str, live_value: object) -> None:
        _persist_setting(self, env_key, env_value, attr_path, live_value)


def _persist_setting(
    page: SettingsPage, env_key: str, env_value: str, attr_path: str, live_value: object
) -> None:
    """Same write-through both `MemoryPage` and `VoicePage` use: update
    the live `Settings` object so the running app sees it immediately,
    and persist to `.env` so it survives a restart."""
    from jarvis.utils.async_utils import fire_and_forget

    node: object = page._settings
    parts = attr_path.split(".")
    for part in parts[:-1]:
        node = getattr(node, part)
    setattr(node, parts[-1], live_value)
    fire_and_forget(page._service.set_env(env_key, env_value))
