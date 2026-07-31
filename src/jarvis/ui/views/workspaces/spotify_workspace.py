"""Spotify workspace -- full-screen player view backed by
``MockSpotifyProvider`` (Milestone 5, section 1 + future integration
interface ``ISpotifyProvider``).
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.features.integrations.mocks import MockSpotifyProvider
from jarvis.ui.async_utils import fire_and_forget
from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleTable,
    StatTile,
    WorkspaceHeader,
)


class SpotifyWorkspace(QWidget):
    def __init__(
        self, provider: MockSpotifyProvider | None = None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._provider = provider or MockSpotifyProvider()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        self._header = WorkspaceHeader(
            "Spotify",
            subtitle="Premium · mock@spotify",
            status_text="Connected",
            status_state="success",
            show_search=False,
        )
        column.addWidget(self._header)

        now_playing_card = SectionCard("Now Playing")
        self._now_playing_label = QLabel("Loading…")
        self._now_playing_label.setObjectName("cardTitle")
        now_playing_card.body.addWidget(self._now_playing_label)
        self._now_playing_sub = QLabel("")
        self._now_playing_sub.setObjectName("rowSubtitle")
        now_playing_card.body.addWidget(self._now_playing_sub)

        controls = QuickActionsRow(
            [("play", "▶", "Play"), ("pause", "⏸", "Pause"), ("next", "⏭", "Next")]
        )
        controls.action_triggered.connect(self._on_control)
        now_playing_card.body.addWidget(controls)
        column.addWidget(now_playing_card)

        stats = CardGrid(columns=3)
        self._tracks_today = StatTile("Tracks Today", "—")
        self._minutes_listened = StatTile("Minutes Listened", "—")
        self._top_genre = StatTile("Top Genre", "Ambient / Lo-fi")
        for tile in (self._tracks_today, self._minutes_listened, self._top_genre):
            stats.add_card(tile)
        column.addWidget(stats)

        recent_card = SectionCard("Recently Played")
        self._table = SimpleTable(["Title", "Artist", "Album", "Duration"])
        recent_card.body.addWidget(self._table)
        column.addWidget(recent_card)

        self._activity = ActivityFeed("Recent Activity")
        column.addWidget(self._activity)
        column.addStretch(1)

        fire_and_forget(self._load())

    async def _load(self) -> None:
        status = await self._provider.get_connection_status()
        now_playing = await self._provider.get_now_playing()
        tracks = await self._provider.list_recent_tracks(10)
        activity = await self._provider.get_recent_activity(6)

        self._header.set_status(
            "Connected" if status.connected else "Disconnected",
            "success" if status.connected else "danger",
        )
        if now_playing:
            state = "▶ Playing" if now_playing["is_playing"] else "⏸ Paused"
            self._now_playing_label.setText(f"{state}: {now_playing['title']}")
            self._now_playing_sub.setText(f"{now_playing['artist']} — {now_playing['album']}")
        self._tracks_today.set_value(str(len(tracks) * 3))
        self._minutes_listened.set_value("142 min", "+18 min", positive=True)
        self._table.set_rows([[t["title"], t["artist"], t["album"], t["duration"]] for t in tracks])
        self._activity.set_items(
            [(a.icon, a.text, a.timestamp.strftime("%H:%M")) for a in activity]
        )

    def _on_control(self, action_id: str) -> None:
        if action_id == "play":
            fire_and_forget(self._provider.play())
        elif action_id == "pause":
            fire_and_forget(self._provider.pause())
        elif action_id == "next":
            fire_and_forget(self._provider.next_track())
        fire_and_forget(self._load())
