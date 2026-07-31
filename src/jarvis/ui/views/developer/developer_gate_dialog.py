"""Administrator-password gate for Developer Mode (Milestone 5, 10A).

JARVIS itself never asks for a password to launch -- this dialog is the
*only* password prompt in the whole app, and it only appears when the
user explicitly asks for Developer Mode. If no password has been
configured yet, the dialog switches to "set a password" mode instead of
silently unlocking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.core.exceptions import InvalidAdminPasswordError
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.developer_mode_service import DeveloperModeService


class DeveloperGateDialog(QDialog):
    def __init__(self, dev_mode: DeveloperModeService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._dev_mode = dev_mode
        self.setWindowTitle("Developer Mode")
        self.setModal(True)
        self.setFixedWidth(380)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 20)
        outer.setSpacing(14)

        title = QLabel("🔒  Developer Mode")
        title.setObjectName("devModeTitle")
        outer.addWidget(title)

        first_run = not dev_mode.is_configured()
        subtitle = QLabel(
            "Set an administrator password to protect Developer Mode."
            if first_run
            else "Enter your administrator password to continue."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("rowSubtitle")
        outer.addWidget(subtitle)

        form = QFormLayout()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Password", self._password)

        self._confirm: QLineEdit | None = None
        if first_run:
            self._confirm = QLineEdit()
            self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow("Confirm", self._confirm)
        outer.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color:#FF3860;")
        self._error_label.setWordWrap(True)
        outer.addWidget(self._error_label)

        submit = QPushButton("Set Password & Unlock" if first_run else "Unlock")
        submit.setProperty("variant", "primary")
        submit.clicked.connect(self._on_submit if not first_run else self._on_set_password)
        outer.addWidget(submit)

        self._password.returnPressed.connect(submit.click)

    def _on_submit(self) -> None:
        try:
            self._dev_mode.unlock(self._password.text())
            self.accept()
        except InvalidAdminPasswordError as err:
            self._error_label.setText(str(err))

    def _on_set_password(self) -> None:

        password = self._password.text()
        confirm = self._confirm.text() if self._confirm else ""
        if password != confirm:
            self._error_label.setText("Passwords do not match.")
            return

        async def _set() -> None:
            try:
                await self._dev_mode.set_password(password)
                self._dev_mode.unlock(password)
                self.accept()
            except InvalidAdminPasswordError as err:
                self._error_label.setText(str(err))

        fire_and_forget(_set())
