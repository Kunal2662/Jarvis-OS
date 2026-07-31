"""API Center -- Milestone 5, section 10B.

Full CRUD over built-in + custom APIs, enable/disable, favorite, mock
validation (health/response-time), and import/export -- all backed by
:class:`ApiCenterService`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from jarvis.domain.api_center.models import ApiDefinition, ApiHealthStatus
from jarvis.ui.components import Card, StatusBadge
from jarvis.ui.views.developer.api_add_edit_dialog import ApiAddEditDialog
from jarvis.utils.async_utils import fire_and_forget

if TYPE_CHECKING:
    from jarvis.services.api_center_service import ApiCenterService

_HEALTH_TO_STATE = {
    ApiHealthStatus.CONNECTED: "connected",
    ApiHealthStatus.AUTH_FAILED: "auth_failed",
    ApiHealthStatus.NETWORK_ERROR: "network_error",
    ApiHealthStatus.INVALID_KEY: "invalid_key",
    ApiHealthStatus.DISABLED: "disabled",
    ApiHealthStatus.UNKNOWN: "unknown",
}


class _ApiRow(Card):
    def __init__(
        self, api: ApiDefinition, view: ApiCenterView, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._api = api
        self._view = view

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 10, 14, 10)
        outer.setSpacing(10)

        star = QPushButton("★" if api.favorite else "☆")
        star.setFlat(True)
        star.setFixedWidth(28)
        star.clicked.connect(self._toggle_favorite)
        outer.addWidget(star)
        self._star = star

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        name = QLabel(f"{api.name}" + ("  🔧" if api.is_builtin else "  ✏"))
        name.setObjectName("rowTitle")
        text_col.addWidget(name)
        sub = QLabel(f"{api.provider} · {api.category.value.replace('_', ' ').title()}")
        sub.setObjectName("rowSubtitle")
        text_col.addWidget(sub)
        outer.addLayout(text_col, 1)

        self._badge = StatusBadge(
            api.last_health.value.replace("_", " ").title(),
            _HEALTH_TO_STATE.get(api.last_health, "unknown"),
        )
        outer.addWidget(self._badge)

        if api.last_response_time_ms is not None:
            rt = QLabel(f"{api.last_response_time_ms:.0f} ms")
            rt.setObjectName("rowSubtitle")
            outer.addWidget(rt)

        validate_btn = QPushButton("Validate")
        validate_btn.setObjectName("cardAction")
        validate_btn.clicked.connect(self._validate)
        outer.addWidget(validate_btn)

        toggle_btn = QPushButton("Disable" if api.enabled else "Enable")
        toggle_btn.setObjectName("cardAction")
        toggle_btn.clicked.connect(self._toggle_enabled)
        outer.addWidget(toggle_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("cardAction")
        edit_btn.clicked.connect(self._edit)
        outer.addWidget(edit_btn)

        if not api.is_builtin:
            delete_btn = QPushButton("Delete")
            delete_btn.setObjectName("cardAction")
            delete_btn.clicked.connect(self._delete)
            outer.addWidget(delete_btn)

    def _toggle_favorite(self) -> None:
        updated = self._view.service.set_favorite(self._api.id, not self._api.favorite)
        self._api = updated
        self._star.setText("★" if updated.favorite else "☆")

    def _toggle_enabled(self) -> None:
        self._view.service.set_enabled(self._api.id, not self._api.enabled)
        self._view.refresh()

    def _edit(self) -> None:
        dialog = ApiAddEditDialog(self._view.service, self._view, existing=self._api)
        if dialog.exec():
            self._view.refresh()

    def _delete(self) -> None:
        self._view.service.delete_api(self._api.id)
        self._view.refresh()

    def _validate(self) -> None:
        fire_and_forget(self._validate_async())

    async def _validate_async(self) -> None:
        result = await self._view.service.validate(self._api.id)
        self._badge.set_state(
            _HEALTH_TO_STATE.get(result.status, "unknown"),
            result.status.value.replace("_", " ").title(),
        )


class ApiCenterView(QWidget):
    def __init__(self, service: ApiCenterService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.service = service

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("API Center")
        title.setObjectName("greetingTitle")
        header.addWidget(title)
        header.addStretch(1)

        add_btn = QPushButton("+ Add API")
        add_btn.setProperty("variant", "primary")
        add_btn.clicked.connect(self._add_api)
        header.addWidget(add_btn)

        validate_all_btn = QPushButton("Validate All")
        validate_all_btn.clicked.connect(self._validate_all)
        header.addWidget(validate_all_btn)

        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import)
        header.addWidget(import_btn)

        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export)
        header.addWidget(export_btn)
        outer.addLayout(header)

        summary = QHBoxLayout()
        self._summary_label = QLabel("")
        self._summary_label.setObjectName("rowSubtitle")
        summary.addWidget(self._summary_label)
        summary.addStretch(1)
        outer.addLayout(summary)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setSpacing(8)
        scroll.setWidget(self._list_container)
        outer.addWidget(scroll, 1)

        self.refresh()

    def refresh(self) -> None:
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        apis = self.service.list_apis()
        connected = sum(1 for a in apis if a.last_health == ApiHealthStatus.CONNECTED)
        self._summary_label.setText(
            f"{len(apis)} installed · {sum(1 for a in apis if a.enabled)} enabled · {connected} connected"
        )
        for api in apis:
            self._list_layout.addWidget(_ApiRow(api, self))
        self._list_layout.addStretch(1)

    def _add_api(self) -> None:
        dialog = ApiAddEditDialog(self.service, self)
        if dialog.exec():
            self.refresh()

    def _validate_all(self) -> None:
        fire_and_forget(self._validate_all_async())

    async def _validate_all_async(self) -> None:
        await self.service.validate_all()
        self.refresh()

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import APIs", "", "JSON Files (*.json)")
        if path:
            self.service.import_from(Path(path))
            self.refresh()

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export APIs", "api_center_export.json", "JSON Files (*.json)"
        )
        if path:
            self.service.export_all(Path(path))
