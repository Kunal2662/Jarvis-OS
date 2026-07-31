"""Agent tools wrapping :class:`~jarvis.services.chat_service.ChatService`.

Deliberately narrow: this is *not* a way for the agent to recurse into
itself. It lets the agent delegate a sub-question to the plain
history-aware chat pipeline for a specific, existing conversation (e.g.
"what did we already decide about X in this conversation") without
re-running its own plan/tool-select/critique loop for something that
doesn't need tools at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.exceptions import ServiceError
from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.chat_service import ChatService

_logger = get_logger("jarvis.agents.tools.chat")


def build_chat_tools(chat: ChatService) -> list[BaseTool]:
    @tool
    async def ask_conversation(conversation_id: str, question: str) -> str:
        """Ask a question against a specific existing chat conversation's
        persisted history (not the agent's own scratch state). Use this to
        pull context from a past conversation by its id, not for general
        reasoning."""
        try:
            return await chat.ask(conversation_id, question)
        except ServiceError as err:
            _logger.warning("ask_conversation tool failed: {}", err)
            return f"Failed: {err}"

    return [ask_conversation]
