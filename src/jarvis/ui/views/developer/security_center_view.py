"""Security Center -- Milestone 5, section 10A.

Real status (not mock): whether Developer Mode has a password
configured, whether a real Fernet secret key is set (governs whether
API Center credentials are encrypted at rest), and OS-keyring usage --
plus a button to change the Developer Mode password via
:class:`DeveloperModeService`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jarvis.ui.components import KeyValueRow, SectionCard, StatusBadge
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.developer_mode_service import DeveloperModeService


class SecurityCenterView(QWidget):
    def __init__(
        self,
        settings: Settings,
        dev_mode_service: DeveloperModeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._dev_mode = dev_mode_service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(14)

        title = QLabel("Security Center")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        card = SectionCard("Status")
        has_secret_key = bool(
            settings.security.secret_key.get_secret_value()
            and settings.security.secret_key.get_secret_value() != "CHANGE_ME_TO_A_FERNET_KEY"
        )
        card.body.addWidget(
            StatusBadge(
                (
                    "API secrets encrypted at rest"
                    if has_secret_key
                    else "Using placeholder Fernet key"
                ),
                "success" if has_secret_key else "warning",
            )
        )
        card.body.addWidget(
            KeyValueRow("OS keyring", "Enabled" if settings.security.use_os_keyring else "Disabled")
        )
        card.body.addWidget(
            KeyValueRow(
                "Developer Mode password",
                "Configured" if dev_mode_service.is_configured() else "Not set",
            )
        )
        card.body.addWidget(
            KeyValueRow(
                "Developer Mode session", "Unlocked" if dev_mode_service.is_unlocked() else "Locked"
            )
        )
        outer.addWidget(card)

        if dev_mode_service.is_configured():
            outer.addWidget(self._build_change_password_form())
        else:
            actions = QHBoxLayout()
            setup_btn = QPushButton("Set Developer Mode Password…")
            setup_btn.clicked.connect(self._open_gate)
            actions.addWidget(setup_btn)
            actions.addStretch(1)
            outer.addLayout(actions)
        outer.addStretch(1)

    def _build_change_password_form(self) -> SectionCard:
        from PySide6.QtWidgets import QFormLayout, QLineEdit

        card = SectionCard("Change Developer Mode Password")
        form = QFormLayout()
        self._current_pw = QLineEdit()
        self._current_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self._new_pw = QLineEdit()
        self._new_pw.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Current password", self._current_pw)
        form.addRow("New password", self._new_pw)
        card.body.addLayout(form)

        self._change_pw_status = QLabel("")
        self._change_pw_status.setObjectName("rowSubtitle")
        card.body.addWidget(self._change_pw_status)

        submit = QPushButton("Update Password")
        submit.setProperty("variant", "primary")
        submit.clicked.connect(self._on_change_password)
        card.body.addWidget(submit)
        return card

    def _on_change_password(self) -> None:

        from jarvis.core.exceptions import InvalidAdminPasswordError

        if not self._dev_mode.verify(self._current_pw.text()):
            self._change_pw_status.setText("Current password is incorrect.")
            return

        async def _update() -> None:
            try:
                await self._dev_mode.set_password(self._new_pw.text())
                self._change_pw_status.setText("Password updated.")
            except InvalidAdminPasswordError as err:
                self._change_pw_status.setText(str(err))

        fire_and_forget(_update())

    def _open_gate(self) -> None:
        from jarvis.ui.views.developer.developer_gate_dialog import DeveloperGateDialog

        DeveloperGateDialog(self._dev_mode, self).exec()
