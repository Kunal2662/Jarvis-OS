"""Generic "Future Integration Interface" placeholder page.

Several sidebar nav items in the official UI (Voice, Automations, Files &
Drive, Browser, Coding, Finance, Smart Home, Calendar, Gmail, Spotify)
point at subsystems that already exist at the service layer (voice
pipeline, automation engine, browser automation, ...) but don't yet have
a dedicated full-screen view of their own -- that's future work, not
this milestone's job. This widget gives every one of those nav items a
real, on-brand landing page today instead of a dead click, using the
same Card component the rest of the dashboard uses.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from jarvis.ui.components import SectionCard


class ComingSoonView(QWidget):
    def __init__(self, title: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)

        card = SectionCard(title)
        body = QLabel(description)
        body.setWordWrap(True)
        body.setObjectName("rowSubtitle")
        card.body.addWidget(body)
        footnote = QLabel("This screen's dedicated UI is a future integration interface.")
        footnote.setObjectName("rowSubtitle")
        card.body.addWidget(footnote)
        outer.addWidget(card)
        outer.addStretch(1)
