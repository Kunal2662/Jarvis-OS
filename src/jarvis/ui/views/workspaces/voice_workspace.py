"""Voice workspace -- dedicated full-screen voice console (Milestone 5,
section 1). The push-to-talk / Chat-page voice pipeline already works;
this gives it a real home screen: live status, waveform-style activity,
recent voice sessions, and voice settings shortcuts. Mock data only.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.ui.components import (
    ActivityFeed,
    CardGrid,
    QuickActionsRow,
    ScrollableColumn,
    SectionCard,
    SimpleListPanel,
    StatTile,
    WorkspaceHeader,
)
from jarvis.ui.widgets.voice_orb import VoiceOrb

_MOCK_SESSIONS = [
    ("Wake word detected", '"Hey Jarvis, what\'s on my calendar?"', 2),
    ("Voice command", '"Play something relaxing on Spotify"', 26),
    ("Voice command", '"Set a reminder for 5 PM"', 74),
    ("Wake word timeout", "No follow-up speech detected", 140),
]


class VoiceWorkspace(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = ScrollableColumn()
        outer.addWidget(scroll)
        column = scroll.column

        header = WorkspaceHeader(
            "Voice",
            subtitle="Wake word, speech recognition, and text-to-speech console.",
            status_text="Listening",
            status_state="success",
            search_placeholder="Search voice sessions…",
        )
        header.add_tool_button("Push to Talk", icon="voice")
        header.add_tool_button("Mute", icon="mute")
        column.addWidget(header)

        orb_card = SectionCard("Voice Console")
        orb_row = QVBoxLayout()
        orb = VoiceOrb()
        orb.setFixedSize(96, 96)
        orb_row.addWidget(orb)
        status_label = QLabel('Wake word: "Hey Jarvis" · Idle, listening for wake word')
        status_label.setObjectName("rowSubtitle")
        orb_row.addWidget(status_label)
        orb_card.body.addLayout(orb_row)
        column.addWidget(orb_card)

        stats = CardGrid(columns=4)
        stats.add_card(StatTile("Sessions Today", "18", "+4", positive=True))
        stats.add_card(StatTile("Avg Response Time", "0.8s", "-0.1s", positive=True))
        stats.add_card(StatTile("Wake Word Accuracy", "97%", "+1%", positive=True))
        stats.add_card(StatTile("TTS Voice", "Aria (Neural)"))
        column.addWidget(stats)

        settings_card = SectionCard("Voice Settings")
        settings_list = SimpleListPanel()
        settings_list.add_row("Wake Word", '"Hey Jarvis"', "Change")
        settings_list.add_row("Input Device", "System Default Microphone", "Change")
        settings_list.add_row("Output Voice", "Aria (Neural, en-US)", "Change")
        settings_list.add_row("Sensitivity", "Medium", "Adjust")
        settings_card.body.addWidget(settings_list)
        column.addWidget(settings_card)

        activity = ActivityFeed("Recent Voice Sessions")
        activity.set_items(
            [
                (
                    icon,
                    f"{title} — {detail}",
                    (datetime.now() - timedelta(seconds=secs)).strftime("%H:%M"),
                )
                for icon, (title, detail, secs) in zip(
                    ["voice", "speaking", "speaking", "timer"], _MOCK_SESSIONS, strict=False
                )
            ]
        )
        column.addWidget(activity)

        actions = QuickActionsRow(
            [
                ("test_mic", "configuration", "Test Microphone"),
                ("retrain_wake", "refresh", "Retrain Wake Word"),
                ("voice_settings", "settings", "Open Settings"),
            ]
        )
        column.addWidget(actions)
        column.addStretch(1)
