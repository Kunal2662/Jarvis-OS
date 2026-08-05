"""Workspace manager -- Milestone 11 Task Group A.

Composes ``WorkspaceService`` with the three subsystems a workspace has
something to say to: Knowledge (M10A), Search (M10A) and Memory (M3).

**Why this exists as a separate class rather than more methods on the
service.** ``WorkspaceService`` owns one domain and talks to one
database. The moment it also imports Knowledge, Search and Memory it
owns four subsystems' failure modes, and every later task group adds
another. Keeping the composition here means the service stays testable
against a database alone, and this class stays a coordinator with no
persistence of its own.

**What it does not do.** It computes nothing and stores nothing. Every
number it returns is produced by the subsystem that owns it -- the same
"collects, never computes" rule ``MCPDiagnostics`` follows, and for the
same reason: a coordinator that derives its own view of the truth
becomes a second source of it.

Task Groups B–D will extend :meth:`context` as they add Tasks, Calendar
and Files. The shape is deliberately additive -- a new subsystem
contributes a key, and nothing already in the payload moves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger

if TYPE_CHECKING:
    from jarvis.core.interfaces.search import SearchResult
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.search_service import SearchService
    from jarvis.services.workspace_ai_service import WorkspaceKnowledgeService
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.workspace_manager")

#: How many related items each optional subsystem contributes to a
#: workspace context. Small on purpose: this payload is a summary a
#: caller acts on, not a full export, and Task Group D's AI context
#: will want to fit it in a prompt.
_RELATED_TOP_K = 5


class WorkspaceManager:
    """Read-side coordinator across the workspace domain and its
    neighbours. Every collaborator except the service itself is
    optional, so a partially-wired container (or a test) degrades to
    less context rather than failing."""

    def __init__(
        self,
        workspace_service: WorkspaceService,
        *,
        knowledge_service: KnowledgeService | None = None,
        search_service: SearchService | None = None,
        memory_service: MemoryService | None = None,
        knowledge_links: WorkspaceKnowledgeService | None = None,
    ) -> None:
        self._workspaces = workspace_service
        self._knowledge = knowledge_service
        self._search = search_service
        self._memory = memory_service
        # Milestone 11 Task Group D. Optional and last, like every other
        # collaborator here, so a container wired only through Task Group
        # A behaves exactly as it did before this existed.
        self._links = knowledge_links

    # ------------------------------------------------------------------
    # Composed reads
    # ------------------------------------------------------------------
    async def overview(self, workspace_id: str) -> dict[str, Any]:
        """One workspace, its projects, its notes and its derived
        metadata -- the four reads a caller would otherwise make in
        sequence, without a fifth subsystem involved."""
        workspace = await self._workspaces.require_workspace(workspace_id)
        projects = await self._workspaces.list_projects(workspace_id=workspace_id)
        notes = await self._workspaces.list_notes(workspace_id=workspace_id)
        metadata = await self._workspaces.metadata(workspace_id)
        settings = await self._workspaces.get_settings(workspace_id)

        return {
            "workspace": {
                "id": workspace.id,
                "name": workspace.name,
                "description": workspace.description,
                "status": workspace.status,
            },
            "settings": settings.as_dict(),
            "metadata": metadata.as_dict(),
            "projects": [{"id": p.id, "name": p.name, "status": p.status} for p in projects],
            "notes": [
                {"id": n.id, "title": n.title, "project_id": n.project_id, "pinned": n.pinned}
                for n in notes
            ],
        }

    async def context(self, workspace_id: str) -> dict[str, Any]:
        """The workspace plus what the *other* subsystems know that
        relates to it.

        Two kinds of relatedness, which Task Group D made it possible to
        tell apart:

        * ``linked_knowledge`` -- entities this workspace's own text
          produced, read from the association table Task Group D added.
          Evidence.
        * ``related_knowledge`` -- entities whose name or description
          shares words with this workspace's. A guess, and still useful:
          a brand-new workspace has produced nothing yet.

        Task Group A's version had only the second and said so, noting
        that inventing an association table before this task group had
        said what it needed would be guessing at a schema. The guess is
        kept rather than replaced, because the two answer different
        questions and dropping the text match would make a workspace
        look unrelated to everything until someone ran an ingestion.
        The payload stays additive, as promised: nothing that was here
        has moved.
        """
        overview = await self.overview(workspace_id)
        workspace = overview["workspace"]
        query = f"{workspace['name']} {workspace['description']}".strip()

        return {
            **overview,
            "linked_knowledge": await self._linked_knowledge(workspace_id),
            "related_knowledge": await self._related_knowledge(query),
            "related_memories": await self._related_memories(query),
        }

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        """Workspace-domain results through the *shared* ``SearchService``
        when one is wired, so a caller gets the same ranking every other
        source is subject to. Without one, the three workspace sources
        are queried directly -- a narrower answer, never a wrong one."""
        if self._search is not None:
            return await self._search.search(query, top_k=top_k)

        results: list[SearchResult] = []
        for search in (
            self._workspaces.search_workspaces,
            self._workspaces.search_projects,
            self._workspaces.search_notes,
        ):
            results.extend(await search(query, top_k=top_k))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    # ------------------------------------------------------------------
    # Optional collaborators -- absent or failing means less context
    # ------------------------------------------------------------------
    async def _linked_knowledge(self, workspace_id: str) -> list[dict[str, Any]]:
        if self._links is None:
            return []
        try:
            return await self._links.entities_for(workspace_id, limit=_RELATED_TOP_K)
        except Exception as err:  # pragma: no cover -- defensive
            _logger.debug("Knowledge links for workspace context failed: {}", err)
            return []

    async def _related_knowledge(self, query: str) -> list[dict[str, Any]]:
        if self._knowledge is None or not query:
            return []
        try:
            hits = await self._knowledge.search(query, top_k=_RELATED_TOP_K)
        except Exception as err:  # pragma: no cover -- defensive
            _logger.debug("Knowledge lookup for workspace context failed: {}", err)
            return []
        return [{"id": h.id, "title": h.title, "score": h.score} for h in hits]

    async def _related_memories(self, query: str) -> list[dict[str, Any]]:
        if self._memory is None or not query:
            return []
        try:
            records = await self._memory.recall(query, top_k=_RELATED_TOP_K)
        except Exception as err:  # pragma: no cover -- defensive
            _logger.debug("Memory recall for workspace context failed: {}", err)
            return []
        return [
            {"id": getattr(r, "id", ""), "content": getattr(r, "content", "")}
            for r in (records or [])
        ]
