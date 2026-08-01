"""Chat page -- composes ChatView + PromptInput + PTT + a conversation
history popup into the single "Chat" nav item's content.

Milestone 2 originally rendered the conversation list as a permanent
sidebar. Milestone 5 replaces the sidebar with the official UI's fixed
nav rail, so that list now lives behind a "History" button on this
page's own toolbar instead -- same functionality, but it no longer
competes with the official UI's sidebar design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from jarvis.ui.components.icons import icon_registry
from jarvis.ui.widgets.chat_view import ChatView
from jarvis.ui.widgets.prompt_input import PromptInput
from jarvis.ui.widgets.push_to_talk_button import PushToTalkButton
from jarvis.ui.widgets.voice_orb import VoiceOrb

if TYPE_CHECKING:
    from jarvis.services.conversation_service import ConversationSummary


class ChatPage(QWidget):
    new_conversation_requested = Signal()
    conversation_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 12, 16, 8)
        toolbar.setSpacing(8)

        new_button = QPushButton("+ New chat")
        new_button.setObjectName("cardAction")
        new_button.clicked.connect(self.new_conversation_requested)
        toolbar.addWidget(new_button)

        self._history_button = QPushButton("History")
        self._history_button.setIcon(icon_registry.qicon("history", size=14))
        self._history_button.setObjectName("cardAction")
        self._history_list = QListWidget()
        self._history_list.setFixedSize(320, 320)
        self._history_list.itemClicked.connect(self._on_history_item_clicked)

        history_menu = QMenu(self._history_button)
        action = QWidgetAction(history_menu)
        action.setDefaultWidget(self._history_list)
        history_menu.addAction(action)
        self._history_button.setMenu(history_menu)
        toolbar.addWidget(self._history_button)
        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        self.chat_view = ChatView(self)
        outer.addWidget(self.chat_view, 1)

        self.voice_orb = VoiceOrb(self)
        self.ptt = PushToTalkButton(self)
        self.prompt = PromptInput(self)

        prompt_row = QHBoxLayout()
        prompt_row.setContentsMargins(12, 0, 12, 12)
        prompt_row.setSpacing(8)
        prompt_row.addWidget(self.voice_orb, 0)
        prompt_row.addWidget(self.ptt, 0)
        prompt_row.addWidget(self.prompt, 1)
        outer.addLayout(prompt_row)

    def set_conversations(self, conversations: list[ConversationSummary]) -> None:
        self._history_list.clear()
        for c in conversations:
            item = QListWidgetItem(c.title or "Untitled")
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            item.setToolTip(c.updated_at.isoformat())
            self._history_list.addItem(item)

    def _on_history_item_clicked(self, item: QListWidgetItem) -> None:
        conv_id = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(conv_id, str):
            self.conversation_selected.emit(conv_id)
            self._history_button.menu().close()
