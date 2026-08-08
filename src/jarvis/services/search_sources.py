"""Concrete :class:`~jarvis.core.interfaces.search.ISearchSource` adapters
(Milestone 10A, extended Milestone 10B and Milestone 11 Task Groups A, B
and C) -- one per searchable subsystem,
each a thin wrapper over an already-real component (``MemoryService``,
``KnowledgeService``, ``IntelligenceService``, ``PluginRegistry``), never
a second implementation of the thing it wraps.

``CommandSearchSource`` deliberately takes a flat, pre-resolved
``list[tuple[name, description]]`` for *agent tools* rather than
importing ``langchain_core``'s ``BaseTool`` or ``agents.tools.registry``
directly -- this module lives in ``services``, and this project's
dependency rule puts ``agents`` *above* ``services`` (agents depends on
services, never the reverse), so resolving the tool registry happens
once, at the DI composition root (``core/di/container.py``), which is
free to import from both layers. ``PluginRegistry`` (a ``core.plugins``
component, below both layers) is queried live at *search* time via
``list_manifests()`` instead of a value snapshotted once at
construction, so a plugin installed or enabled after ``SearchService``
was first wired still shows up in Command Search without a stale index.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.interfaces.search import SearchResult

if TYPE_CHECKING:
    from jarvis.core.plugins.registry import PluginRegistry
    from jarvis.services.calendar_service import CalendarService
    from jarvis.services.file_service import (
        AttachmentService,
        FileService,
        FolderService,
    )
    from jarvis.services.intelligence_service import IntelligenceService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.reminder_service import ReminderService
    from jarvis.services.smart_home_service import SmartHomeService
    from jarvis.services.task_service import TaskService
    from jarvis.services.workspace_service import WorkspaceService


class MemorySearchSource:
    """Wraps :meth:`MemoryService.search` (hybrid mode) -- no separate
    memory index, no duplicated recall logic."""

    source_type = "memory"

    def __init__(self, memory: MemoryService) -> None:
        self._memory = memory

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        records = await self._memory.search(query, mode="hybrid", top_k=top_k)
        return [
            SearchResult(
                id=r.id,
                title=r.content[:80],
                content=r.content,
                source=self.source_type,
                score=r.score,
                uri=f"memory://{r.id}",
                metadata={"memory_type": r.memory_type, "pinned": r.pinned},
            )
            for r in records
        ]


class KnowledgeSearchSource:
    """Wraps :meth:`KnowledgeService.search` -- knowledge-graph entity
    lookup, no separate index."""

    source_type = "knowledge"

    def __init__(self, knowledge: KnowledgeService) -> None:
        self._knowledge = knowledge

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._knowledge.search(query, top_k=top_k)


class GoalSearchSource:
    """Wraps :meth:`IntelligenceService.search` (Milestone 10B) -- goal
    title/description lookup, no separate index. Proves the Search
    Provider Registry's own extensibility requirement: a new searchable
    subsystem registers here without any change to ``SearchService``
    itself."""

    source_type = "goals"

    def __init__(self, intelligence: IntelligenceService) -> None:
        self._intelligence = intelligence

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._intelligence.search(query, top_k=top_k)


class CommandSearchSource:
    """Command Search -- the backing index for M8's Command Palette shell.

    Indexes two real, already-shipped sources of invokable commands:
    agent tools (``agents/tools/registry.py``'s ``build_tool_registry``,
    resolved once by the DI container -- the tool list is genuinely
    static once services are wired, the same assumption
    ``AgentOrchestrator.start()`` already makes) and plugin-declared
    commands (``PluginManifest.commands``, read fresh from
    ``PluginRegistry.list_manifests()`` on every query, never cached).
    Plain case-insensitive substring scoring -- commands are a small,
    closed set; no embedding/LLM call is warranted for this source.
    """

    source_type = "commands"

    def __init__(
        self,
        tools: list[tuple[str, str]],
        *,
        plugin_registry: PluginRegistry | None = None,
    ) -> None:
        """*tools* is ``[(name, description), ...]``."""
        self._tools = tools
        self._plugin_registry = plugin_registry

    def _current_commands(self) -> list[tuple[str, str, str]]:
        commands: list[tuple[str, str, str]] = [(n, d, "tool") for n, d in self._tools]
        if self._plugin_registry is not None:
            for manifest in self._plugin_registry.list_manifests():
                commands.extend((c.id, c.description, "plugin_command") for c in manifest.commands)
        return commands

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        tokens = [t.lower() for t in query.split() if t]
        if not tokens:
            return []
        scored: list[tuple[float, tuple[str, str, str]]] = []
        for name, description, kind in self._current_commands():
            haystack = f"{name} {description}".lower()
            hits = sum(1 for t in tokens if t in haystack)
            if hits == 0:
                continue
            score = hits / len(tokens)
            scored.append((score, (name, description, kind)))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [
            SearchResult(
                id=f"{kind}:{name}",
                title=name,
                content=description,
                source=self.source_type,
                score=score,
                uri=f"command://{kind}/{name}",
                metadata={"kind": kind},
            )
            for score, (name, description, kind) in scored[:top_k]
        ]


# ---------------------------------------------------------------------------
# Milestone 11 Task Group A — Workspace Foundation
# ---------------------------------------------------------------------------
class WorkspaceSearchSource:
    """Wraps :meth:`WorkspaceService.search_workspaces`.

    Three sources rather than one combined "workspace" source, because
    ``SearchService`` filters and reports *by* ``source_type``: a caller
    asking for notes should not have to receive workspaces and filter
    them out, and the Command Palette will want to weight them
    differently. The cost is three thin classes; the alternative is a
    source whose results a caller must re-partition."""

    source_type = "workspaces"

    def __init__(self, workspaces: WorkspaceService) -> None:
        self._workspaces = workspaces

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._workspaces.search_workspaces(query, top_k=top_k)


class ProjectSearchSource:
    """Wraps :meth:`WorkspaceService.search_projects`."""

    source_type = "projects"

    def __init__(self, workspaces: WorkspaceService) -> None:
        self._workspaces = workspaces

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._workspaces.search_projects(query, top_k=top_k)


class NoteSearchSource:
    """Wraps :meth:`WorkspaceService.search_notes` -- the one workspace
    source with real scoring rather than a flat status weight, since a
    note has a title and a body that can match independently."""

    source_type = "notes"

    def __init__(self, workspaces: WorkspaceService) -> None:
        self._workspaces = workspaces

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._workspaces.search_notes(query, top_k=top_k)


# ---------------------------------------------------------------------------
# Milestone 11 Task Group B — Productivity Core
# ---------------------------------------------------------------------------
class TaskSearchSource:
    """Wraps :meth:`TaskService.search`. The service does the scoring --
    an open, urgent task outranks a cancelled one -- so this stays the
    thin adapter every other source in this module is."""

    source_type = "tasks"

    def __init__(self, tasks: TaskService) -> None:
        self._tasks = tasks

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._tasks.search(query, top_k=top_k)


class CalendarSearchSource:
    """Wraps :meth:`CalendarService.search`, which returns events *and*
    calendars under one source type: someone searching "standup" wants
    the meeting and someone searching "Work" wants the calendar, and
    making them choose a source first would be the tool asking the user
    to know its schema. ``metadata["kind"]`` distinguishes them."""

    source_type = "calendar"

    def __init__(self, calendar: CalendarService) -> None:
        self._calendar = calendar

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._calendar.search(query, top_k=top_k)


class ReminderSearchSource:
    """Wraps :meth:`ReminderService.search`."""

    source_type = "reminders"

    def __init__(self, reminders: ReminderService) -> None:
        self._reminders = reminders

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._reminders.search(query, top_k=top_k)


# ---------------------------------------------------------------------------
# Milestone 11 Task Group C — File Platform
# ---------------------------------------------------------------------------
class FileSearchSource:
    """Wraps :meth:`FileService.search_files`.

    The only source in this module whose corpus includes extracted file
    *contents* -- ``FileService`` joins the index record into its query,
    so a search for a phrase inside a Markdown note finds the file. That
    is still keyword matching over stored text, not semantic search:
    there is no embedding, no vector store and no summarisation behind
    this source, and claiming otherwise by naming it "semantic" would be
    the kind of overstatement Task Group C set out to avoid.
    """

    source_type = "files"

    def __init__(self, files: FileService) -> None:
        self._files = files

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._files.search_files(query, top_k=top_k)


class FolderSearchSource:
    """Wraps :meth:`FolderService.search_folders` -- name and path
    lookup, so "where did I put the invoices folder" is answerable
    without walking the tree."""

    source_type = "folders"

    def __init__(self, folders: FolderService) -> None:
        self._folders = folders

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._folders.search_folders(query, top_k=top_k)


class IntegrationSearchSource:
    """Milestone 11 Task Group E -- one connected vendor's own search.

    Registered when an integration connects and unregistered when it
    disconnects, which is the first source in this module with a
    *runtime* lifetime. That is M10A's provider registry working exactly
    as its docstring promised -- *"a future module or plugin can add a
    new ISearchSource without this class ever changing"* -- and it is
    why ``source_type`` is namespaced per integration rather than a
    single shared ``"integrations"``: two connected vendors are two
    sources a caller can filter between, and one source that silently
    changed meaning when a second vendor connected would be worse than
    either.

    **The vendor does the searching.** This queries the endpoint the
    spec names (Gmail's ``q``, Drive's ``q``, People's ``query``) rather
    than listing everything and filtering locally -- which would be
    slower, spend quota, and give worse answers than the vendor's own
    index.

    **A disconnected or unauthorized integration returns nothing rather
    than raising.** ``SearchService`` already treats a failing source as
    excluded, but an integration that is merely not connected is not a
    failure worth logging on every keystroke.
    """

    def __init__(self, service: Any, spec: Any) -> None:
        self.source_type = f"integration:{spec.integration_id}"
        self._service = service
        self._spec = spec

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query or not self._spec.search_operation:
            return []
        try:
            rows = await self._service.search(self._spec.integration_id, query, top_k=top_k)
        except Exception:
            # Not connected, not authorized, or the vendor is down. The
            # shared SearchService excludes a failing source already;
            # returning empty keeps that quiet for the common case.
            return []

        results: list[SearchResult] = []
        for row in rows[:top_k]:
            identifier = str(row.get("id") or row.get("name") or row.get("resourceName") or "")
            results.append(
                SearchResult(
                    id=identifier,
                    title=_vendor_title(row) or identifier,
                    content=_vendor_snippet(row),
                    source=self.source_type,
                    score=1.0,
                    uri=f"integration://{self._spec.integration_id}/{identifier}",
                    metadata={
                        "integration_id": self._spec.integration_id,
                        "vendor": self._spec.vendor,
                    },
                )
            )
        return results


def _vendor_title(row: dict[str, Any]) -> str:
    """A human label from a vendor row.

    Vendors disagree about which key holds "the name of this thing", and
    there is no standard to defer to. Trying the documented ones in
    order and falling back to the id keeps a result readable without a
    per-vendor extractor -- the failure mode is a duller title, never a
    wrong one.
    """
    for key in ("subject", "title", "name", "summary", "displayName", "filename"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    names = row.get("names")
    if isinstance(names, list) and names and isinstance(names[0], dict):
        return str(names[0].get("displayName") or "")
    return ""


def _vendor_snippet(row: dict[str, Any]) -> str:
    for key in ("snippet", "description", "body", "notes", "mimeType"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


class AttachmentSearchSource:
    """Wraps :meth:`AttachmentService.search_attachments`.

    Separate from ``FileSearchSource`` even though both can surface the
    same file, because they answer different questions: one is "find
    this file", the other is "find where this file was used". A single
    combined source would return the file twice with no way to tell the
    two hits apart."""

    source_type = "attachments"

    def __init__(self, attachments: AttachmentService) -> None:
        self._attachments = attachments

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._attachments.search_attachments(query, top_k=top_k)


class HomeSearchSource:
    """Wraps :meth:`SmartHomeService.search_homes` (Milestone 12 Task
    Group A)."""

    source_type = "homes"

    def __init__(self, smart_home: SmartHomeService) -> None:
        self._smart_home = smart_home

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._smart_home.search_homes(query, top_k=top_k)


class DeviceSearchSource:
    """Wraps :meth:`SmartHomeService.search_devices` (Milestone 12 Task
    Group A). Zones, rooms and device groups are not their own sources
    -- see ``core/di/container.py``'s registration comment for why."""

    source_type = "devices"

    def __init__(self, smart_home: SmartHomeService) -> None:
        self._smart_home = smart_home

    async def search(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        return await self._smart_home.search_devices(query, top_k=top_k)
