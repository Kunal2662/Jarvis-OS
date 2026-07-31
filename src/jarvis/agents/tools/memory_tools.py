"""Agent tools wrapping :class:`~jarvis.services.memory_service.MemoryService`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.memory_service import MemoryService

_logger = get_logger("jarvis.agents.tools.memory")


def build_memory_tools(memory: MemoryService) -> list[BaseTool]:
    @tool
    async def remember(content: str, memory_type: str = "long_term") -> str:
        """Save a fact, preference, or note to JARVIS's long-term memory so it
        can be recalled in future conversations. Use this when the user shares
        something worth remembering (a preference, a decision, a project
        detail). ``memory_type`` is one of: conversation, long_term,
        preference, project, task, file, ai_context."""
        try:
            memory_id = await memory.remember(content, memory_type=memory_type)
        except Exception as err:
            _logger.warning("remember tool failed: {}", err)
            return f"Failed to store memory: {err}"
        return f"Stored memory {memory_id}."

    @tool
    async def recall_memory(query: str, top_k: int = 5) -> str:
        """Search JARVIS's stored memories for facts relevant to a query.
        Returns the matching notes, most relevant first, or a message saying
        nothing was found."""
        records = await memory.recall(query, top_k=top_k)
        if not records:
            return "No relevant memories found."
        return "\n".join(f"- {r.content}" for r in records)

    return [remember, recall_memory]
