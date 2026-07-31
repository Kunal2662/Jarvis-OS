"""Add/Edit API dialog -- Milestone 5, section 10B.

Includes live Smart API Detection: as the user types in the Name field,
a suggestions label updates from :meth:`ApiCenterService.suggest`, and
clicking a suggestion chip prefills provider/category/base URL from the
matching built-in template.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from jarvis.domain.api_center.models import ApiAuthType, ApiCategory, ApiDefinition
from jarvis.features.api_center.registry import builtin_templates

if TYPE_CHECKING:
    from jarvis.services.api_center_service import ApiCenterService


class ApiAddEditDialog(QDialog):
    def __init__(
        self,
        service: ApiCenterService,
        parent: QWidget | None = None,
        *,
        existing: ApiDefinition | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._existing = existing
        self.setWindowTitle("Edit API" if existing else "Add API")
        self.setModal(True)
        self.resize(460, 560)

        self._by_name = {t.name: t for t in builtin_templates()}

        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        self._name = QLineEdit(existing.name if existing else "")
        self._name.setPlaceholderText("e.g. OpenAI, GitHub, or a custom name")
        self._name.textChanged.connect(self._on_name_changed)
        self._suggestions_label = QLabel("")
        self._suggestions_label.setObjectName("rowSubtitle")
        self._suggestions_label.setWordWrap(True)

        self._provider = QLineEdit(existing.provider if existing else "")
        self._base_url = QLineEdit(existing.base_url if existing else "")
        self._category = QComboBox()
        for cat in ApiCategory:
            self._category.addItem(cat.value.replace("_", " ").title(), cat)
        if existing:
            self._category.setCurrentIndex(self._category.findData(existing.category))

        self._auth_type = QComboBox()
        for auth in ApiAuthType:
            self._auth_type.addItem(auth.value.replace("_", " ").title(), auth)
        if existing:
            self._auth_type.setCurrentIndex(self._auth_type.findData(existing.auth_type))

        self._api_key = QLineEdit(existing.api_key if existing else "")
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._bearer_token = QLineEdit(existing.bearer_token if existing else "")
        self._bearer_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._secret = QLineEdit(existing.secret if existing else "")
        self._secret.setEchoMode(QLineEdit.EchoMode.Password)
        self._oauth_id = QLineEdit(existing.oauth_client_id if existing else "")
        self._oauth_secret = QLineEdit(existing.oauth_client_secret if existing else "")
        self._oauth_secret.setEchoMode(QLineEdit.EchoMode.Password)

        self._headers = QPlainTextEdit()
        self._headers.setPlaceholderText("One per line, e.g.\nX-Api-Version: 2024-01")
        if existing and existing.headers:
            self._headers.setPlainText("\n".join(f"{k}: {v}" for k, v in existing.headers.items()))
        self._headers.setFixedHeight(70)

        self._description = QPlainTextEdit(existing.description if existing else "")
        self._description.setFixedHeight(60)

        form = QFormLayout()
        form.addRow("API Name", self._name)
        form.addRow("", self._suggestions_label)
        form.addRow("Provider", self._provider)
        form.addRow("Category", self._category)
        form.addRow("Base URL", self._base_url)
        form.addRow("Auth Type", self._auth_type)
        form.addRow("API Key", self._api_key)
        form.addRow("Bearer Token", self._bearer_token)
        form.addRow("Secret", self._secret)
        form.addRow("OAuth Client ID", self._oauth_id)
        form.addRow("OAuth Client Secret", self._oauth_secret)
        form.addRow("Headers", self._headers)
        form.addRow("Description", self._description)
        outer.addLayout(form)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Save")
        save.setProperty("variant", "primary")
        save.clicked.connect(self._on_save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        outer.addLayout(buttons)

    # ------------------------------------------------------------------
    def _on_name_changed(self, text: str) -> None:
        suggestions = self._service.suggest(text, limit=4)
        self._suggestions_label.setText(
            "Suggestions: " + ", ".join(s.name for s in suggestions) if suggestions and text else ""
        )
        # Auto-fill from an exact built-in match, like a real smart-detect flow.
        template = self._by_name.get(text.strip())
        if template is not None and not self._existing:
            self._provider.setText(template.provider)
            self._base_url.setText(template.base_url)
            self._category.setCurrentIndex(self._category.findData(template.category))
            self._auth_type.setCurrentIndex(self._auth_type.findData(template.auth_type))
            if not self._description.toPlainText():
                self._description.setPlainText(template.description)

    def _parse_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        for line in self._headers.toPlainText().splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                headers[key.strip()] = value.strip()
        return headers

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            self._suggestions_label.setText("API Name is required.")
            return

        kwargs = dict(
            name=name,
            provider=self._provider.text().strip(),
            category=self._category.currentData(),
            auth_type=self._auth_type.currentData(),
            base_url=self._base_url.text().strip(),
            api_key=self._api_key.text(),
            bearer_token=self._bearer_token.text(),
            secret=self._secret.text(),
            oauth_client_id=self._oauth_id.text().strip(),
            oauth_client_secret=self._oauth_secret.text(),
            headers=self._parse_headers(),
            description=self._description.toPlainText().strip(),
        )

        try:
            if self._existing:
                self._service.update_api(self._existing.id, **kwargs)
            else:
                self._service.add_api(ApiDefinition(**kwargs))
        except Exception as err:
            self._suggestions_label.setText(str(err))
            return
        self.accept()
