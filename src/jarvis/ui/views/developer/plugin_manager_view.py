"""Plugin Manager -- Milestone 5, section 7 (expanded from the original
10A placeholder).

There is still no real third-party plugin loader -- that remains
genuine future work and is never faked here. What this view now shows
is the full architecture the brief asks for: installed-plugin details
(version, author, dependencies, permissions), Enable/Disable/Reload
wired to a mock ``IPluginProvider`` (``MockPluginProvider``), a
Marketplace placeholder tab, and Install/Uninstall/Update controls that
exist and are visibly disabled with an honest tooltip rather than
hidden -- "prepare architecture only", exactly as instructed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from jarvis.domain.voice_announcements.events import AnnouncementEvent
from jarvis.features.plugins.mock_provider import MockPluginProvider
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import Card, CardGrid, StatTile, StatusBadge

if TYPE_CHECKING:
    from jarvis.core.config.settings import Settings
    from jarvis.services.voice_announcement_service import VoiceAnnouncementService

_STATUS_STATE = {"enabled": "success", "disabled": "neutral", "reloading": "warning"}


class PluginManagerView(QWidget):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        *,
        voice_announcer: VoiceAnnouncementService | None = None,
    ) -> None:
        super().__init__(parent)
        self._provider = MockPluginProvider(settings.resolved_data_dir / "plugins")
        self._voice_announcer = voice_announcer

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(10)

        title = QLabel("Plugin Manager")
        title.setObjectName("greetingTitle")
        outer.addWidget(title)

        self._stats = CardGrid(columns=2)
        outer.addWidget(self._stats)

        self._tabs = QTabWidget()
        self._installed_tab = QWidget()
        self._installed_layout = QVBoxLayout(self._installed_tab)
        self._installed_layout.setSpacing(8)
        self._tabs.addTab(self._installed_tab, "Installed")

        self._marketplace_tab = QWidget()
        self._marketplace_layout = QVBoxLayout(self._marketplace_tab)
        self._marketplace_layout.setSpacing(8)
        self._tabs.addTab(self._marketplace_tab, "Marketplace")
        outer.addWidget(self._tabs, 1)

        fire_and_forget(self._load())

    async def _load(self) -> None:
        installed = await self._provider.list_installed()
        marketplace = await self._provider.list_marketplace()
        self._render_installed(installed)
        self._render_marketplace(marketplace)

    def _render_installed(self, plugins: list[dict]) -> None:
        self._stats.clear()
        enabled_count = sum(1 for p in plugins if p["enabled"])
        self._stats.add_card(StatTile("Installed Plugins", str(len(plugins))))
        self._stats.add_card(StatTile("Enabled", str(enabled_count)))

        while self._installed_layout.count():
            item = self._installed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not plugins:
            empty = QLabel("No plugins installed yet.")
            empty.setObjectName("rowSubtitle")
            self._installed_layout.addWidget(empty)
        for plugin in plugins:
            self._installed_layout.addWidget(self._build_plugin_row(plugin))
        self._installed_layout.addStretch(1)

    def _render_marketplace(self, listings: list[dict]) -> None:
        while self._marketplace_layout.count():
            item = self._marketplace_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        note = QLabel("Marketplace placeholder -- browsing only, no real backend yet.")
        note.setObjectName("rowSubtitle")
        self._marketplace_layout.addWidget(note)

        for listing in listings:
            card = Card()
            layout = QHBoxLayout(card)
            layout.setContentsMargins(14, 10, 14, 10)
            name = QLabel(f"{listing['name']}  ·  v{listing['version']}")
            name.setObjectName("rowTitle")
            layout.addWidget(name, 1)
            author = QLabel(f"by {listing['author']}")
            author.setObjectName("rowSubtitle")
            layout.addWidget(author)
            install_btn = QPushButton("Install")
            install_btn.setEnabled(False)
            install_btn.setToolTip("Future placeholder -- no plugin loader exists yet.")
            layout.addWidget(install_btn)
            self._marketplace_layout.addWidget(card)
        self._marketplace_layout.addStretch(1)

    def _build_plugin_row(self, plugin: dict) -> QWidget:
        row = Card()
        layout = QVBoxLayout(row)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        name = QLabel(plugin["name"])
        name.setObjectName("rowTitle")
        top.addWidget(name)
        version = QLabel(f"v{plugin['version']}")
        version.setObjectName("rowSubtitle")
        top.addWidget(version)
        top.addStretch(1)
        top.addWidget(
            StatusBadge(plugin["status"].title(), _STATUS_STATE.get(plugin["status"], "neutral"))
        )
        layout.addLayout(top)

        details = QLabel(
            f"Author: {plugin['author']}  ·  Source: {plugin['source']}  ·  "
            f"Dependencies: {', '.join(plugin['dependencies']) or 'None'}"
        )
        details.setObjectName("rowSubtitle")
        details.setWordWrap(True)
        layout.addWidget(details)

        permissions = QLabel(f"Permissions: {', '.join(plugin['permissions']) or 'None requested'}")
        permissions.setObjectName("rowSubtitle")
        layout.addWidget(permissions)

        actions = QHBoxLayout()
        actions.setSpacing(6)

        toggle_btn = QPushButton("Disable" if plugin["enabled"] else "Enable")
        toggle_btn.setObjectName("cardAction")
        toggle_btn.clicked.connect(
            lambda _c=False, pid=plugin["id"], en=plugin["enabled"]: fire_and_forget(
                self._toggle(pid, en)
            )
        )
        actions.addWidget(toggle_btn)

        reload_btn = QPushButton("Reload")
        reload_btn.setObjectName("cardAction")
        reload_btn.setEnabled(plugin["enabled"])
        reload_btn.clicked.connect(
            lambda _c=False, pid=plugin["id"]: fire_and_forget(self._reload(pid))
        )
        actions.addWidget(reload_btn)

        update_btn = QPushButton("Update")
        update_btn.setEnabled(False)
        update_btn.setToolTip("Future placeholder -- no update channel exists for plugins yet.")
        actions.addWidget(update_btn)

        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setEnabled(False)
        uninstall_btn.setToolTip("Future placeholder -- no plugin loader exists yet.")
        actions.addWidget(uninstall_btn)

        actions.addStretch(1)
        layout.addLayout(actions)
        return row

    async def _toggle(self, plugin_id: str, currently_enabled: bool) -> None:
        if currently_enabled:
            await self._provider.disable(plugin_id)
            if self._voice_announcer is not None:
                await self._voice_announcer.announce_event(AnnouncementEvent.PLUGIN_DISABLED)
        else:
            await self._provider.enable(plugin_id)
            if self._voice_announcer is not None:
                await self._voice_announcer.announce_event(AnnouncementEvent.PLUGIN_ENABLED)
        await self._load()

    async def _reload(self, plugin_id: str) -> None:
        await self._provider.reload(plugin_id)
        await self._load()
