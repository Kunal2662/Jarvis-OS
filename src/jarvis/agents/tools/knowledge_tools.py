"""Agent tools wrapping :class:`~jarvis.services.knowledge_service.KnowledgeService`
(Milestone 10A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.knowledge_service import KnowledgeService

_logger = get_logger("jarvis.agents.tools.knowledge")


def build_knowledge_tools(knowledge: KnowledgeService) -> list[BaseTool]:
    @tool
    async def ask_knowledge(query: str) -> str:
        """Ask what JARVIS knows about a topic, person, or project (e.g.
        "what do you know about Project X"). Synthesizes a coherent
        answer from the knowledge graph and memory, not just a keyword
        match."""
        try:
            return await knowledge.ask(query)
        except Exception as err:
            _logger.warning("ask_knowledge tool failed: {}", err)
            return f"Couldn't answer that: {err}"

    @tool
    async def search_knowledge(query: str, top_k: int = 5) -> str:
        """Search JARVIS's knowledge graph for entities (people, projects,
        files, topics) matching a query. Returns matching entities, most
        relevant first, or a message saying nothing was found."""
        results = await knowledge.search(query, top_k=top_k)
        if not results:
            return "No matching knowledge entities found."
        return "\n".join(f"- {r.title}: {r.content}" for r in results)

    return [ask_knowledge, search_knowledge]
