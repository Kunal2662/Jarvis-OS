"""Plugin Manager -- Milestone 5, section 7.

**Reads the real Plugin Platform** (Aug 2026 backlog pass). When this
view was written there was no plugin loader, so it rendered two
invented plugins and a three-entry invented catalogue against a mock
provider. Milestone 9 Task Group C shipped the real thing -- registry,
loader, sandbox, permission model, marketplace -- and this view was
simply never rewired, so it kept showing fabricated rows next to a
working runtime.

Every row now comes from
:class:`~jarvis.features.plugins.registry_provider.PluginRegistryProvider`
over the live ``PluginRegistry``. Enable, Disable and Reload perform
real lifecycle transitions. An install with no plugins renders an empty
state rather than invented examples.

Install/Uninstall/Update stay visibly disabled with a tooltip that says
why: the registry implements all three, but each needs a *source
directory* the user picks, and that file-dialog flow is not part of
this pass. Disabled-and-explained beats hidden, and beats a button that
silently does nothing.
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
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import Card, CardGrid, StatTile, StatusBadge

if TYPE_CHECKING:
    from jarvis.core.interfaces.providers import IPluginProvider
    from jarvis.services.voice_announcement_service import VoiceAnnouncementService

_STATUS_STATE = {
    "enabled": "success",
    "disabled": "neutral",
    "reloading": "warning",
    "discovered": "neutral",
    # A plugin that crashed on load is not the same as one the user
    # switched off, and the badge says so.
    "failed": "danger",
}


class PluginManagerView(QWidget):
    def __init__(
        self,
        provider: IPluginProvider,
        parent: QWidget | None = None,
        *,
        voice_announcer: VoiceAnnouncementService | None = None,
    ) -> None:
        """*provider* is injected rather than constructed here, so this
        view depends on the port and the composition root decides which
        implementation backs it -- the same rule every other view in
        this dashboard already follows."""
        super().__init__(parent)
        self._provider = provider
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

        if not listings:
            empty = QLabel(
                "No marketplace index configured. Point "
                "`plugins.marketplace_index_path` at an index to browse."
            )
            empty.setObjectName("rowSubtitle")
            empty.setWordWrap(True)
            self._marketplace_layout.addWidget(empty)

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
            install_btn.setToolTip(
                "Installing needs a package source to install from; "
                "use POST /api/v1/plugins/install for now."
            )
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

        # A failed plugin explains itself rather than showing a bare badge.
        if plugin.get("error"):
            error = QLabel(f"Error: {plugin['error']}")
            error.setObjectName("rowSubtitle")
            error.setWordWrap(True)
            layout.addWidget(error)

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
        update_btn.setToolTip(
            "Updating needs a source directory to update from; use the REST API for now."
        )
        actions.addWidget(update_btn)

        uninstall_btn = QPushButton("Uninstall")
        uninstall_btn.setEnabled(False)
        uninstall_btn.setToolTip(
            "Uninstalling from this view is not wired yet; "
            "use DELETE /api/v1/plugins/{id} for now."
        )
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
