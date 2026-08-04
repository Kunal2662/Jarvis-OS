"""Module Manager -- Milestone 5, section 6 (expanded from the original
10A placeholder).

Lists the application's own internal modules with a real (settings-flag
seeded) enabled/disabled starting state, then layers in the richer
shape the brief asks for -- version, dependencies, status, Enable /
Disable / Reload / Update actions -- backed by a mock in-memory
``ModuleRegistryService`` since there's no real hot-reload/update
machinery to wire those actions to yet. Future Install / Remove are
shown as explicitly disabled placeholders rather than being hidden, so
the eventual real feature has an obvious landing spot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from jarvis.features.modules.mock_registry import ModuleInfo, ModuleRegistryService
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import Card, CardGrid, StatTile, StatusBadge

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings

_STATUS_STATE = {
    "running": "success",
    "stopped": "neutral",
    "reloading": "warning",
    "error": "danger",
}


class ModuleManagerView(QWidget):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._registry = ModuleRegistryService(settings)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Module Manager")
        title.setObjectName("greetingTitle")
        header_row.addWidget(title)
        header_row.addStretch(1)
        install_btn = QPushButton("+ Install Module…")
        install_btn.setEnabled(False)
        install_btn.setToolTip("Future placeholder -- no module installer exists yet.")
        header_row.addWidget(install_btn)
        outer.addLayout(header_row)

        self._stats = CardGrid(columns=3)
        outer.addWidget(self._stats)

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(8)
        outer.addLayout(self._rows_container)
        outer.addStretch(1)

        self._render()

    def _render(self) -> None:
        self._stats.clear()
        installed = self._registry.list_installed()
        disabled = self._registry.list_disabled()
        self._stats.add_card(StatTile("Installed Modules", str(len(installed))))
        self._stats.add_card(StatTile("Disabled Modules", str(len(disabled))))
        self._stats.add_card(StatTile("Total Modules", str(len(self._registry.list_all()))))

        while self._rows_container.count():
            item = self._rows_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for module in self._registry.list_all():
            self._rows_container.addWidget(self._build_row(module))

    def _build_row(self, module: ModuleInfo) -> QWidget:
        row = Card()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(module.name)
        name.setObjectName("rowTitle")
        top.addWidget(name)
        version = QLabel(f"v{module.version}")
        version.setObjectName("rowSubtitle")
        top.addWidget(version)
        top.addStretch(1)
        top.addWidget(
            StatusBadge(module.status.title(), _STATUS_STATE.get(module.status, "neutral"))
        )
        layout.addLayout(top)

        desc = QLabel(module.description)
        desc.setObjectName("rowSubtitle")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        deps = QLabel(
            f"Dependencies: {', '.join(module.dependencies) if module.dependencies else 'None'}"
        )
        deps.setObjectName("rowSubtitle")
        layout.addWidget(deps)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        enable_btn = QPushButton("Disable" if module.enabled else "Enable")
        enable_btn.setObjectName("cardAction")
        enable_btn.clicked.connect(
            lambda _c=False, n=module.name, en=module.enabled: fire_and_forget(self._toggle(n, en))
        )
        actions.addWidget(enable_btn)

        reload_btn = QPushButton("Reload")
        reload_btn.setObjectName("cardAction")
        reload_btn.setEnabled(module.enabled)
        reload_btn.clicked.connect(lambda _c=False, n=module.name: fire_and_forget(self._reload(n)))
        actions.addWidget(reload_btn)

        update_btn = QPushButton("Check for Update")
        update_btn.setObjectName("cardAction")
        update_btn.clicked.connect(
            lambda _c=False, n=module.name, b=update_btn: fire_and_forget(self._check_update(n, b))
        )
        actions.addWidget(update_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.setEnabled(False)
        remove_btn.setToolTip("Future placeholder -- module removal isn't supported yet.")
        actions.addWidget(remove_btn)

        actions.addStretch(1)
        layout.addLayout(actions)
        return row

    async def _toggle(self, name: str, currently_enabled: bool) -> None:
        if currently_enabled:
            await self._registry.disable(name)
        else:
            await self._registry.enable(name)
        self._render()

    async def _reload(self, name: str) -> None:
        self._render()
        await self._registry.reload(name)
        self._render()

    async def _check_update(self, name: str, button: QPushButton) -> None:
        button.setEnabled(False)
        button.setText("Checking…")
        result = await self._registry.check_update(name)
        if result["update_available"]:
            button.setText(f"Update to v{result['latest_version']}")
        elif result.get("checked", True):
            button.setText("Up to Date")
        else:
            # Nothing was actually asked, so "Up to Date" would be a
            # claim this app cannot make.
            button.setText("No update channel")
            button.setToolTip(result.get("detail", ""))
        button.setEnabled(True)
