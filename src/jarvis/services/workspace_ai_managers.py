"""AI Workspace managers -- Milestone 11 Task Group D.

``WorkspaceContextManager`` / ``WorkspaceRetriever``: the read-side
coordinators for the AI layer, following ``WorkspaceManager`` and the
Task Group B and C managers exactly -- they **collect and never
compute**, hold no state, persist nothing, and treat every collaborator
except their own required one as optional, so a partially-wired
container degrades to less context rather than failing.

* :class:`WorkspaceContextManager` -- *what is going on in this
  workspace, small enough to put in a prompt.* The capability Task
  Groups A, B and C each deferred to this one: their ``context()``
  methods say "Task Group D replaces this method's body without changing
  its shape", and the shape they preserved is what this assembles.
* :class:`WorkspaceRetriever` -- *what in this workspace matches this
  question.* Retrieval scoped to one workspace, over the **shared**
  ``SearchService`` rather than an index of its own.

**Why the context manager composes managers rather than services.**
Every number it needs already has an owner that produces it:
``TaskManager.agenda`` knows what is overdue, ``CalendarManager``
expands recurrence rules, ``FileManager.overview`` totals bytes. Reading
those through their managers keeps one implementation of each answer.
Reaching past them into the services and recomputing would be a second
implementation of exactly the arithmetic those managers exist to own --
the "second source of truth" this repository has spent several
milestones removing.

**Why the retriever post-filters instead of pushing a workspace filter
down.** ``ISearchSource.search`` takes a query and a ``top_k`` and
nothing else, and widening that port would change every one of the
thirteen sources registered against it, most of which have no workspace
concept at all. Filtering the ranked results by the ``workspace_id``
the workspace-domain sources already put in ``SearchResult.metadata`` is
honest about what it is: one shared ranking, narrowed. The cost is
over-fetching, which is why the multiplier is explicit and tunable
rather than hidden.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jarvis.core.logging.logger import get_logger
from jarvis.domain.ai_workspace.models import (
    DEFAULT_CONTEXT_BUDGET_CHARS,
    DEFAULT_ITEM_CHARS,
    DEFAULT_SECTION_ITEMS,
    ContextItem,
    ContextSection,
    WorkspaceContext,
    pack,
)

if TYPE_CHECKING:
    from jarvis.core.interfaces.search import SearchResult
    from jarvis.services.calendar_service import CalendarService
    from jarvis.services.file_managers import FileManager
    from jarvis.services.file_service import FileService
    from jarvis.services.knowledge_service import KnowledgeService
    from jarvis.services.memory_service import MemoryService
    from jarvis.services.productivity_managers import (
        CalendarManager,
        ReminderManager,
        TaskManager,
    )
    from jarvis.services.search_service import SearchService
    from jarvis.services.task_service import TaskService
    from jarvis.services.workspace_ai_service import WorkspaceKnowledgeService
    from jarvis.services.workspace_service import WorkspaceService

_logger = get_logger("jarvis.services.workspace_ai_managers")

#: How many results to ask the shared index for, per result wanted, when
#: narrowing to one workspace. Four is a judgement, not a measurement:
#: it makes a workspace holding a quarter of the matching corpus fill a
#: page, and it bounds the work at four pages for a workspace holding
#: none. A caller wanting certainty rather than a bound passes a larger
#: ``top_k``.
DEFAULT_OVERFETCH = 4

#: Sources with no workspace notion at all. Excluded from a scoped
#: retrieval by default and included only when a caller opts in, because
#: "search my workspace" returning a global memory is a surprising
#: answer to a scoped question.
GLOBAL_SOURCES: frozenset[str] = frozenset({"memory", "knowledge", "goals", "commands"})

#: Which task statuses count as still on someone's plate. Two of Task
#: Group B's four -- ``done`` and ``cancelled`` are history, and putting
#: them in a context would spend the budget telling a model what is
#: already finished.
OPEN_TASK_STATUSES: tuple[str, ...] = ("todo", "in_progress")


class WorkspaceContextManager:
    """Assembles one workspace's full picture, budgeted for a prompt."""

    def __init__(
        self,
        workspace_service: WorkspaceService,
        *,
        task_manager: TaskManager | None = None,
        task_service: TaskService | None = None,
        calendar_manager: CalendarManager | None = None,
        reminder_manager: ReminderManager | None = None,
        file_manager: FileManager | None = None,
        knowledge_links: WorkspaceKnowledgeService | None = None,
        knowledge_service: KnowledgeService | None = None,
        memory_service: MemoryService | None = None,
        budget_chars: int = DEFAULT_CONTEXT_BUDGET_CHARS,
        section_items: int = DEFAULT_SECTION_ITEMS,
        item_chars: int = DEFAULT_ITEM_CHARS,
    ) -> None:
        self._workspaces = workspace_service
        self._tasks = task_manager
        # The one service among these collaborators, and only for the
        # plain listing no manager exposes -- see ``_tasks_section``.
        self._task_service = task_service
        self._calendar = calendar_manager
        self._reminders = reminder_manager
        self._files = file_manager
        self._links = knowledge_links
        self._knowledge = knowledge_service
        self._memory = memory_service
        self._budget_chars = budget_chars
        self._section_items = section_items
        self._item_chars = item_chars

    async def context(
        self, workspace_id: str, *, budget_chars: int | None = None
    ) -> WorkspaceContext:
        """Every wired subsystem's view of one workspace, ordered and
        packed into a character budget.

        Raises if the workspace does not exist -- that is a caller
        error, not a missing collaborator. Everything *else* degrades:
        a subsystem that is unwired or throwing costs its section and
        nothing more, which is what lets this run in a container wired
        for one milestone or all of them.
        """
        workspace = await self._workspaces.require_workspace(workspace_id)
        sections: list[ContextSection] = [await self._workspace_section(workspace)]
        for build in (
            self._projects_section,
            self._tasks_section,
            self._calendar_section,
            self._reminders_section,
            self._notes_section,
            self._files_section,
            self._knowledge_section,
            self._memories_section,
        ):
            sections.append(await build(workspace))

        return pack(
            sections,
            workspace_id=workspace_id,
            workspace_name=workspace.name,
            budget_chars=budget_chars or self._budget_chars,
            item_chars=self._item_chars,
        )

    # ------------------------------------------------------------------
    # Sections -- one per subsystem, each independently degradable
    # ------------------------------------------------------------------
    async def _workspace_section(self, workspace: Any) -> ContextSection:
        items = [
            ContextItem(
                title=workspace.name,
                detail=workspace.description,
                uri=f"workspace://{workspace.id}",
            )
        ]
        metadata = await _safe(self._workspaces.metadata(workspace.id), "workspace metadata")
        if metadata is not None:
            items.append(
                ContextItem(
                    title="At a glance",
                    detail=(
                        f"status {workspace.status}, "
                        f"{metadata.active_project_count} active of "
                        f"{metadata.project_count} project(s), "
                        f"{metadata.note_count} note(s)"
                    ),
                )
            )
        return ContextSection(name="workspace", items=tuple(items), total=len(items))

    async def _projects_section(self, workspace: Any) -> ContextSection:
        projects = await _safe(
            self._workspaces.list_projects(workspace_id=workspace.id), "projects"
        )
        rows = list(projects or [])
        # Active first: a context under budget pressure should lose the
        # archived projects, not the ones being worked on.
        rows.sort(key=lambda project: (project.status != "active", project.name))
        items = tuple(
            ContextItem(
                title=project.name,
                detail=f"{project.status}: {project.description}".strip(": "),
                uri=f"project://{project.id}",
            )
            for project in rows[: self._section_items]
        )
        return ContextSection(name="projects", items=items, total=len(rows))

    async def _tasks_section(self, workspace: Any) -> ContextSection:
        """Overdue, then due soon, then everything else still open.

        The third group matters more than it looks. ``TaskManager.agenda``
        answers "what is due", which is the right question for a badge
        and the wrong one for a context: a task with no due date is in
        neither bucket, and most tasks have no due date. Without this the
        assistant would be told a workspace has one task and shown none
        of them.

        The urgency judgement still comes from the manager that owns it
        -- nothing here recomputes what "overdue" means. Only the plain
        listing comes from the service, because no manager exposes one.
        """
        if self._tasks is None:
            return ContextSection(name="tasks")
        agenda = await _safe(self._tasks.agenda(workspace.id), "task agenda")
        if agenda is None:
            return ContextSection(name="tasks")

        overdue = list(agenda.get("overdue", []))
        due_soon = list(agenda.get("due_soon", []))
        items: list[ContextItem] = []
        counts = agenda.get("status_counts") or {}
        if counts:
            items.append(
                ContextItem(
                    title="Task counts",
                    detail=", ".join(
                        f"{status}: {count}" for status, count in sorted(counts.items())
                    ),
                )
            )
        items.extend(_task_item(row, "OVERDUE") for row in overdue)
        items.extend(_task_item(row, "due soon") for row in due_soon)

        dated = {row.get("id") for row in overdue + due_soon}
        for task in await self._open_tasks(workspace.id):
            if task.id in dated:
                continue
            items.append(
                ContextItem(
                    title=f"[open] {task.title}",
                    detail=f"{task.status}/{task.priority}, due {_iso(task.due_at) or 'n/a'}",
                    uri=f"task://{task.id}",
                )
            )

        return ContextSection(
            name="tasks",
            items=tuple(items[: self._section_items]),
            total=len(items),
        )

    async def _open_tasks(self, workspace_id: str) -> list[Any]:
        if self._task_service is None:
            return []
        rows: list[Any] = []
        for status in OPEN_TASK_STATUSES:
            found = await _safe(
                self._task_service.list_tasks(workspace_id=workspace_id, status=status),
                "open tasks",
            )
            rows.extend(found or [])
        return rows

    async def _calendar_section(self, workspace: Any) -> ContextSection:
        if self._calendar is None:
            return ContextSection(name="calendar")
        agenda = await _safe(self._calendar.agenda(workspace.id), "calendar agenda")
        if agenda is None:
            return ContextSection(name="calendar")
        occurrences = list(agenda.get("occurrences", []))
        items = tuple(
            ContextItem(
                title=str(row.get("title", "")),
                detail=f"{row.get('starts_at', '')} ({row.get('category', 'general')})",
                uri=f"event://{row.get('event_id', '')}",
            )
            for row in occurrences[: self._section_items]
        )
        return ContextSection(name="calendar", items=items, total=len(occurrences))

    async def _reminders_section(self, workspace: Any) -> ContextSection:
        if self._reminders is None:
            return ContextSection(name="reminders")
        digest = await _safe(
            self._reminders.due_digest(workspace_id=workspace.id), "reminder digest"
        )
        if digest is None:
            return ContextSection(name="reminders")
        due = list(digest.get("due", []))
        items = tuple(
            ContextItem(
                title=str(row.get("title", "")),
                detail=f"due {row.get('remind_at', '')}",
                uri=f"reminder://{row.get('id', '')}",
            )
            for row in due[: self._section_items]
        )
        return ContextSection(name="reminders", items=items, total=len(due))

    async def _notes_section(self, workspace: Any) -> ContextSection:
        notes = await _safe(self._workspaces.list_notes(workspace_id=workspace.id), "notes")
        rows = list(notes or [])
        items = tuple(
            ContextItem(
                title=f"{note.title}{' (pinned)' if note.pinned else ''}",
                detail=note.content,
                uri=f"note://{note.id}",
            )
            for note in rows[: self._section_items]
        )
        return ContextSection(name="notes", items=items, total=len(rows))

    async def _files_section(self, workspace: Any) -> ContextSection:
        if self._files is None:
            return ContextSection(name="files")
        overview = await _safe(self._files.overview(workspace.id), "file overview")
        if overview is None:
            return ContextSection(name="files")
        recent = list(overview.get("recent_files", []))
        items: list[ContextItem] = [
            ContextItem(
                title="File totals",
                detail=(
                    f"{overview.get('file_count', 0)} file(s), "
                    f"{overview.get('total_bytes', 0)} byte(s)"
                ),
            )
        ]
        items.extend(
            ContextItem(
                title=str(row.get("filename", "")),
                detail=str(row.get("description") or row.get("relative_path") or ""),
                uri=f"file://{row.get('id', '')}",
            )
            for row in recent[: self._section_items]
        )
        return ContextSection(
            name="files", items=tuple(items[: self._section_items]), total=len(items)
        )

    async def _knowledge_section(self, workspace: Any) -> ContextSection:
        """Linked entities first, text matches only if there are none.

        The order is the whole point of this task group. A link was
        produced by *this workspace's own text*; a text match is
        something in the graph that happens to share a word with the
        workspace's name. Preferring the second when the first exists
        would keep the guess and discard the evidence.
        """
        if self._links is not None:
            entities = await _safe(
                self._links.entities_for(workspace.id, limit=self._section_items),
                "workspace knowledge links",
            )
            if entities:
                items = tuple(
                    ContextItem(
                        title=str(row.get("name", "")),
                        detail=(
                            f"{row.get('entity_type', 'other')}: {row.get('description', '')} "
                            f"[{row.get('link_count', 0)} link(s)]"
                        ),
                        uri=str(row.get("uri", "")),
                    )
                    for row in entities
                )
                return ContextSection(name="knowledge", items=items, total=len(entities))

        if self._knowledge is None:
            return ContextSection(name="knowledge")
        query = f"{workspace.name} {workspace.description}".strip()
        hits = await _safe(
            self._knowledge.search(query, top_k=self._section_items), "knowledge search"
        )
        rows = list(hits or [])
        items = tuple(ContextItem(title=hit.title, detail=hit.content, uri=hit.uri) for hit in rows)
        return ContextSection(name="knowledge", items=items, total=len(rows))

    async def _memories_section(self, workspace: Any) -> ContextSection:
        if self._memory is None:
            return ContextSection(name="memories")
        query = f"{workspace.name} {workspace.description}".strip()
        if not query:
            return ContextSection(name="memories")
        records = await _safe(self._memory.recall(query, top_k=self._section_items), "memory")
        rows = list(records or [])
        items = tuple(
            ContextItem(title=getattr(record, "content", "")[:80], detail="") for record in rows
        )
        return ContextSection(name="memories", items=items, total=len(rows))


class WorkspaceRetriever:
    """Workspace-scoped retrieval over the shared ``SearchService``."""

    def __init__(
        self,
        workspace_service: WorkspaceService,
        *,
        search_service: SearchService | None = None,
        calendar_service: CalendarService | None = None,
        task_service: TaskService | None = None,
        file_service: FileService | None = None,
        overfetch: int = DEFAULT_OVERFETCH,
    ) -> None:
        self._workspaces = workspace_service
        self._search = search_service
        self._calendar = calendar_service
        self._tasks = task_service
        self._files = file_service
        self._overfetch = max(overfetch, 1)

    async def retrieve(
        self,
        workspace_id: str,
        query: str,
        *,
        top_k: int = 10,
        include_global: bool = False,
    ) -> list[SearchResult]:
        """Results from *query* that belong to *workspace_id*.

        Through the shared ``SearchService`` when one is wired, so a hit
        is ranked against every other source before being narrowed;
        otherwise the workspace-domain services are queried directly --
        a narrower answer, never a wrong one. Same fallback contract
        every manager since Task Group A has used.
        """
        await self._workspaces.require_workspace(workspace_id)
        query = (query or "").strip()
        if not query:
            return []

        calendar_ids = await self._calendar_ids(workspace_id)
        if self._search is not None:
            candidates = await self._search.search(query, top_k=top_k * self._overfetch)
        else:
            candidates = await self._fallback_search(workspace_id, query, top_k=top_k)

        kept = [
            result
            for result in candidates
            if _belongs(result, workspace_id, calendar_ids, include_global=include_global)
        ]
        kept.sort(key=lambda result: result.score, reverse=True)
        return kept[:top_k]

    async def _calendar_ids(self, workspace_id: str) -> frozenset[str]:
        """The workspace's calendar ids, so an event result can be
        scoped.

        A calendar event carries no ``workspace_id`` -- Task Group B put
        it on the calendar deliberately, so the two can never disagree
        -- which leaves the join to whoever needs it. One query per
        retrieval, not one per result.
        """
        if self._calendar is None:
            return frozenset()
        calendars = await _safe(
            self._calendar.list_calendars(workspace_id=workspace_id), "calendars"
        )
        return frozenset(calendar.id for calendar in calendars or [])

    async def _fallback_search(
        self, workspace_id: str, query: str, *, top_k: int
    ) -> list[SearchResult]:
        results: list[SearchResult] = []
        searches = [
            self._workspaces.search_workspaces,
            self._workspaces.search_projects,
            self._workspaces.search_notes,
        ]
        if self._tasks is not None:
            searches.append(self._tasks.search)
        if self._calendar is not None:
            searches.append(self._calendar.search)
        if self._files is not None:
            searches.append(self._files.search_files)
        for search in searches:
            found = await _safe(search(query, top_k=top_k * self._overfetch), "fallback search")
            results.extend(found or [])
        return results


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------
def _belongs(
    result: SearchResult,
    workspace_id: str,
    calendar_ids: frozenset[str],
    *,
    include_global: bool,
) -> bool:
    """Whether one ranked result is inside *workspace_id*.

    Four rules, in the order they can be decided cheaply. Anything this
    cannot place is excluded -- a scoped search that leaks an unrelated
    workspace's note is a privacy-shaped bug, and "I could not tell"
    must resolve to "not this workspace" rather than to a guess.
    """
    if result.metadata.get("workspace_id") == workspace_id:
        return True
    if result.source == "workspaces" and result.id == workspace_id:
        return True
    if result.source == "calendar":
        calendar_id = result.metadata.get("calendar_id")
        return bool(calendar_id) and calendar_id in calendar_ids
    return include_global and result.source in GLOBAL_SOURCES


def _task_item(row: dict[str, Any], marker: str) -> ContextItem:
    return ContextItem(
        title=f"[{marker}] {row.get('title', '')}",
        detail=(
            f"{row.get('status', '')}/{row.get('priority', '')}, due {row.get('due_at') or 'n/a'}"
        ),
        uri=f"task://{row.get('id', '')}",
    )


def _iso(moment: Any) -> str | None:
    return moment.isoformat() if moment else None


async def _safe(awaitable: Any, label: str) -> Any:
    """Awaits *awaitable*, returning ``None`` if it fails.

    One helper rather than a base-class method, the same choice
    ``productivity_managers.related_items`` made and for the same reason:
    these managers need identical defensive plumbing and sharing it
    through a function keeps them siblings instead of a hierarchy.
    """
    try:
        return await awaitable
    except Exception as err:  # a failing subsystem costs its section
        _logger.debug("Workspace context lookup for {} failed: {}", label, err)
        return None
