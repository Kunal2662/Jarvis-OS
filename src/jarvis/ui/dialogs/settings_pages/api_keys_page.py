"""API keys page — secrets are masked and never displayed in plaintext."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

from jarvis.ui.dialogs.settings_pages.base import SettingsPage
from jarvis.utils.async_utils import fire_and_forget


class APIKeysPage(SettingsPage):
    id = "api_keys"
    title = "API Keys"
    category = "AI"

    def build(self) -> None:
        title = QLabel(self.title)
        title.setStyleSheet("font-size:20px; font-weight:600;")
        self._layout.addWidget(title)

        warn = QLabel(
            "Keys are stored in the local <code>.env</code> file and are never "
            "shown in plaintext after you save them. To rotate a key, paste "
            "the new value and press <b>Save</b>."
        )
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#6D8BAA;")
        self._layout.addWidget(warn)

        form = QFormLayout()
        form.setContentsMargins(0, 8, 0, 0)
        form.setSpacing(12)

        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._openai_key.setPlaceholderText("sk-…  (leave blank to keep current value)")
        form.addRow("OpenAI API Key", self._openai_key)

        self._openai_org = QLineEdit(self._settings.openai.org)
        self._openai_org.setPlaceholderText("(optional)")
        form.addRow("OpenAI Organization", self._openai_org)

        self._openai_base = QLineEdit(self._settings.openai.base_url)
        form.addRow("OpenAI Base URL", self._openai_base)

        self._save = QPushButton("Save")
        self._save.setProperty("variant", "primary")
        self._save.clicked.connect(self._on_save)

        self._status = QLabel("")
        self._status.setStyleSheet("color:#0E9F6E;")

        self._layout.addLayout(form)
        self._layout.addWidget(self._save)
        self._layout.addWidget(self._status)
        self._layout.addStretch(1)

    def _on_save(self) -> None:
        fire_and_forget(self._save_async())

    async def _save_async(self) -> None:
        try:
            key = self._openai_key.text().strip()
            if key:
                await self._service.set_env("JARVIS_OPENAI_API_KEY", key)
                self._openai_key.clear()

            org = self._openai_org.text().strip()
            await self._service.set_env("JARVIS_OPENAI_ORG", org)

            base = self._openai_base.text().strip()
            if base:
                await self._service.set_env("JARVIS_OPENAI_BASE_URL", base)

            self._status.setText("Saved. Restart JARVIS for changes to take effect.")
        except Exception as err:
            self._status.setStyleSheet("color:#FF3860;")
            self._status.setText(f"Failed: {err}")
