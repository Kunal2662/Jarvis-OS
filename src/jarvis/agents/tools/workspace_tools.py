"""Agent tools wrapping
:class:`~jarvis.services.workspace_ai_service.WorkspaceAssistantService`
(Milestone 11 Task Group D).

Five tools over one service rather than one tool per workspace
subsystem: the agent needs to *find* a workspace, *see* one, *search*
inside one and *ask about* one, and every one of those questions is
already answered by the assistant's own facade. Wiring the agent
straight to ``WorkspaceService``/``TaskService``/``FileService`` instead
would give it four ways to assemble a context and no reason to prefer
any of them -- the second-implementation problem this task group exists
to close.

Every tool returns text. That is the contract ``BaseTool`` has in this
codebase (see ``knowledge_tools`` and ``intelligence_tools``), and a
tool returning structured data the responder then has to re-render
would put formatting in two places.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.tools import BaseTool, tool

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.services.workspace_ai_service import WorkspaceAssistantService

_logger = get_logger("jarvis.agents.tools.workspace")


def build_workspace_tools(assistant: WorkspaceAssistantService) -> list[BaseTool]:
    @tool
    async def list_workspaces() -> str:
        """List the user's workspaces with their ids. Call this first
        when the user names a workspace but you do not have its id --
        every other workspace tool takes an id, not a name."""
        workspaces = await assistant.list_workspaces()
        if not workspaces:
            return "No workspaces exist yet."
        return "\n".join(f"- [{w['id']}] {w['name']} ({w['status']})" for w in workspaces)

    @tool
    async def workspace_context(workspace_id: str) -> str:
        """Get the current state of one workspace: its projects, overdue
        and upcoming tasks, calendar, reminders, notes, files and what
        the knowledge graph associates with it. Use this before
        answering anything about what the user is working on."""
        try:
            context = await assistant.context(workspace_id)
        except Exception as err:
            _logger.warning("workspace_context tool failed: {}", err)
            return f"Couldn't read that workspace: {err}"
        return context.render() or "That workspace is empty."

    @tool
    async def search_workspace(workspace_id: str, query: str, top_k: int = 5) -> str:
        """Search inside one workspace -- its projects, notes, tasks,
        calendar events and files. Results outside this workspace are
        excluded, so this is the right tool when the user asks about
        something "in" a particular workspace."""
        try:
            results = await assistant.retrieve(workspace_id, query, top_k=top_k)
        except Exception as err:
            _logger.warning("search_workspace tool failed: {}", err)
            return f"Couldn't search that workspace: {err}"
        if not results:
            return "Nothing in that workspace matches."
        return "\n".join(f"- [{r.source}] {r.title}: {r.content[:160]}" for r in results)

    @tool
    async def ask_workspace(workspace_id: str, question: str) -> str:
        """Answer a question about one workspace, grounded in that
        workspace's own projects, tasks, notes and files. Prefer this
        over answering from memory when the question is about the user's
        actual work."""
        try:
            result = await assistant.ask(workspace_id, question)
        except Exception as err:
            _logger.warning("ask_workspace tool failed: {}", err)
            return f"Couldn't answer that: {err}"
        return result.answer

    @tool
    async def summarize_workspace(workspace_id: str) -> str:
        """Summarize what is going on in one workspace: what is in
        progress, what is overdue, what is coming up."""
        try:
            result = await assistant.summarize(workspace_id)
        except Exception as err:
            _logger.warning("summarize_workspace tool failed: {}", err)
            return f"Couldn't summarize that workspace: {err}"
        return result.answer

    return [
        list_workspaces,
        workspace_context,
        search_workspace,
        ask_workspace,
        summarize_workspace,
    ]
