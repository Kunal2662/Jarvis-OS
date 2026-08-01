"""Smart Home workspace -- device control dashboard backed by
``MockSmartHomeProvider`` (Milestone 5, section 1 + future integration
interface ``ISmartHomeProvider``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from jarvis.features.integrations.mocks import MockSmartHomeProvider
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import (
    ActivityFeed,
    Card,
    CardGrid,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    StatTile,
    StatusBadge,
    WorkspaceHeader,
)
from jarvis.ui.components.buttons import PillButton
from jarvis.ui.components.icons import Icon

_DEVICE_ICON_KEYS = {
    "light": "device_light",
    "climate": "device_climate",
    "lock": "lock",
    "camera": "device_camera",
}


class SmartHomeWorkspace(QWidget):
    def __init__(
        self, provider: MockSmartHomeProvider | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._provider = provider or MockSmartHomeProvider()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        self._column = scroll.column

        self._header = WorkspaceHeader(
            "Smart Home",
            subtitle="Devices, rooms, and automations.",
            status_text="Connected",
            status_state="success",
            search_placeholder="Search devices…",
        )
        self._header.add_tool_button("Add Device", icon="add")
        self._column.addWidget(self._header)

        stats = CardGrid(columns=3)
        self._online_tile = StatTile("Devices Online", "—")
        self._total_tile = StatTile("Total Devices", "—")
        self._automations_tile = StatTile("Active Automations", "3")
        for tile in (self._online_tile, self._total_tile, self._automations_tile):
            stats.add_card(tile)
        self._column.addWidget(stats)

        self._devices_card = SectionCard("Devices")
        self._device_grid = CardGrid(columns=2)
        self._devices_card.body.addWidget(self._device_grid)
        self._column.addWidget(self._devices_card)

        self._activity = ActivityFeed("Recent Activity")
        self._column.addWidget(self._activity)

        actions = QuickActionsRow(
            [
                ("all_off", "power_off", "All Off"),
                ("goodnight", "moon", "Goodnight Scene"),
                ("connect", "link", "Connect Hub"),
            ]
        )
        self._column.addWidget(actions)
        self._column.addStretch(1)

        fire_and_forget(self._load())

    async def _load(self) -> None:
        status = await self._provider.get_connection_status()
        devices = await self._provider.list_devices()
        activity = await self._provider.get_recent_activity(6)

        self._header.set_status(
            "Connected" if status.connected else "Disconnected",
            "success" if status.connected else "danger",
        )
        online = sum(1 for d in devices if d["online"])
        self._online_tile.set_value(str(online))
        self._total_tile.set_value(str(len(devices)))

        self._device_grid.clear()
        for device in devices:
            self._device_grid.add_card(self._build_device_tile(device))

        self._activity.set_items(
            [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity]
        )

    def _build_device_tile(self, device: dict) -> QWidget:
        card = Card()
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header_row = QHBoxLayout()
        icon_key = _DEVICE_ICON_KEYS.get(device["type"], "device_generic")
        header_row.addWidget(Icon(icon_key, size=16))
        name = QLabel(device["name"])
        name.setObjectName("cardTitle")
        header_row.addWidget(name, 1)
        header_row.addWidget(
            StatusBadge(
                "Online" if device["online"] else "Offline",
                "success" if device["online"] else "danger",
            )
        )
        layout.addLayout(header_row)

        state_label = QLabel(f"State: {device['state']}")
        state_label.setObjectName("rowSubtitle")
        layout.addWidget(state_label)

        toggle = PillButton("", "Toggle")
        toggle.clicked.connect(lambda _c=False, d=device["id"]: fire_and_forget(self._toggle(d)))
        layout.addWidget(toggle)
        return card

    async def _toggle(self, device_id: str) -> None:
        devices = await self._provider.list_devices()
        current = next((d for d in devices if d["id"] == device_id), None)
        if current is None:
            return
        new_state = "off" if current["state"] in ("on", "unlocked") else "on"
        await self._provider.set_device_state(device_id, {"state": new_state})
        await self._load()
