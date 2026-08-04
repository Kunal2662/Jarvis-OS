"""Workspace service -- Milestone 11 Task Group A.

Owns the Workspace / Project / Note domain: lifecycle, CRUD, settings,
derived metadata, the search hook, and event publishing. Structured to
match ``IntelligenceService`` exactly -- an ``IDatabase`` opened per
call via ``db.session()``, a repository constructed inside that
session, an optional ``EventBus``, and a ``search()`` method a
``SearchSource`` wraps.

**What this service deliberately does not do.** It does not touch
Knowledge, Search or Memory; composing those with this domain is
``WorkspaceManager``'s single job, and doing it here would put four
subsystems' concerns in one class. It also does not own Tasks,
Calendar, Reminders or Files -- those are Task Groups B and C, and the
point of shipping this one first is that they get a container to hang
off rather than each inventing their own.

**Validation posture.** Statuses and note formats are checked against
the closed vocabularies in ``domain/workspace/models.py`` and raise
``ServiceError`` on a miss, the same way ``IntelligenceService`` rejects
an empty goal title. A typo'd status would otherwise persist happily
and then silently fail to match any filter.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.search import SearchResult
from jarvis.core.logging.logger import get_logger
from jarvis.domain.workspace.models import (
    NOTE_FORMATS,
    PROJECT_STATUSES,
    WORKSPACE_STATUSES,
    WorkspaceMetadata,
    WorkspaceSettings,
)
from jarvis.infrastructure.database.repositories import (
    NoteRepository,
    ProjectRepository,
    WorkspaceRepository,
)

if TYPE_CHECKING:
    from jarvis.core.events.event_bus import EventBus
    from jarvis.core.interfaces.database import IDatabase
    from jarvis.infrastructure.database.models import Note, Project, Workspace

_logger = get_logger("jarvis.services.workspace")

#: A note matched on its title is a better hit than one matched deep in
#: its body, and a pinned note is one the user already said matters.
#: Deterministic weights, not a learned ranking -- the same posture
#: M10A set for search scoring and M10B repeated for suggestions.
_NOTE_TITLE_SCORE = 1.0
_NOTE_CONTENT_SCORE = 0.6
_PINNED_BOOST = 1.2


class WorkspaceService:
    def __init__(
        self,
        *,
        database: IDatabase,
        event_bus: EventBus | None = None,
    ) -> None:
        self._db = database
        self._event_bus = event_bus

    # ------------------------------------------------------------------
    # Workspace lifecycle
    # ------------------------------------------------------------------
    async def create_workspace(
        self,
        name: str,
        *,
        description: str = "",
        settings: WorkspaceSettings | None = None,
    ) -> Workspace:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a workspace with an empty name.")

        settings_json = json.dumps((settings or WorkspaceSettings()).as_dict())
        async with self._db.session() as sess:
            workspace = await WorkspaceRepository(sess).add(  # type: ignore[arg-type]
                name, description=description, settings_json=settings_json
            )
            workspace_id = workspace.id
        await self._publish_workspace(workspace_id, action="created")
        _logger.info("Workspace created: {} ({})", name, workspace_id)
        return await self.require_workspace(workspace_id)

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        async with self._db.session() as sess:
            return await WorkspaceRepository(sess).get(workspace_id)  # type: ignore[arg-type]

    async def require_workspace(self, workspace_id: str) -> Workspace:
        """``get_workspace`` for callers that treat absence as an error,
        so each one does not repeat the same ``if is None: raise``."""
        workspace = await self.get_workspace(workspace_id)
        if workspace is None:
            raise ServiceError(f"Workspace {workspace_id!r} does not exist.")
        return workspace

    async def list_workspaces(self, *, status: str | None = None) -> list[Workspace]:
        _validate_status(status, WORKSPACE_STATUSES, "workspace")
        async with self._db.session() as sess:
            return await WorkspaceRepository(sess).list_workspaces(status=status)  # type: ignore[arg-type]

    async def update_workspace(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        settings: WorkspaceSettings | None = None,
    ) -> Workspace | None:
        _validate_status(status, WORKSPACE_STATUSES, "workspace")
        settings_json = json.dumps(settings.as_dict()) if settings is not None else None

        async with self._db.session() as sess:
            workspace = await WorkspaceRepository(sess).update(  # type: ignore[arg-type]
                workspace_id,
                name=name,
                description=description,
                status=status,
                settings_json=settings_json,
            )
            if workspace is None:
                return None
        # "archived" is a distinct action rather than a generic update:
        # it is the one status change a subscriber is likely to act on.
        action = "archived" if status == "archived" else "updated"
        await self._publish_workspace(workspace_id, action=action)
        return await self.get_workspace(workspace_id)

    async def delete_workspace(self, workspace_id: str) -> bool:
        async with self._db.session() as sess:
            deleted = await WorkspaceRepository(sess).delete(workspace_id)  # type: ignore[arg-type]
        if deleted:
            await self._publish_workspace(workspace_id, action="deleted")
        return deleted

    # ------------------------------------------------------------------
    # Settings + metadata
    # ------------------------------------------------------------------
    async def get_settings(self, workspace_id: str) -> WorkspaceSettings:
        workspace = await self.require_workspace(workspace_id)
        return _decode_settings(workspace.settings_json)

    async def metadata(self, workspace_id: str) -> WorkspaceMetadata:
        """Derived, never stored -- see ``domain/workspace/models.py``
        for why. Three aggregate counts plus one ``max()``, not a
        collection load."""
        await self.require_workspace(workspace_id)
        async with self._db.session() as sess:
            projects, active, notes = await WorkspaceRepository(sess).counts(  # type: ignore[arg-type]
                workspace_id
            )
            last_activity = await NoteRepository(sess).last_activity_at(  # type: ignore[arg-type]
                workspace_id
            )
        return WorkspaceMetadata(
            workspace_id=workspace_id,
            project_count=projects,
            active_project_count=active,
            note_count=notes,
            last_activity_at=last_activity,
        )

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    async def create_project(
        self, workspace_id: str, name: str, *, description: str = ""
    ) -> Project:
        name = (name or "").strip()
        if not name:
            raise ServiceError("Cannot create a project with an empty name.")
        # Checked here rather than relying on the foreign key so the
        # caller gets "that workspace does not exist" instead of an
        # IntegrityError from three layers down.
        await self.require_workspace(workspace_id)

        async with self._db.session() as sess:
            project = await ProjectRepository(sess).add(  # type: ignore[arg-type]
                workspace_id, name, description=description
            )
            project_id = project.id
        await self._publish_project(project_id, workspace_id, action="created")
        return await self.require_project(project_id)

    async def get_project(self, project_id: str) -> Project | None:
        async with self._db.session() as sess:
            return await ProjectRepository(sess).get(project_id)  # type: ignore[arg-type]

    async def require_project(self, project_id: str) -> Project:
        project = await self.get_project(project_id)
        if project is None:
            raise ServiceError(f"Project {project_id!r} does not exist.")
        return project

    async def list_projects(
        self, *, workspace_id: str | None = None, status: str | None = None
    ) -> list[Project]:
        _validate_status(status, PROJECT_STATUSES, "project")
        async with self._db.session() as sess:
            return await ProjectRepository(sess).list_projects(  # type: ignore[arg-type]
                workspace_id=workspace_id, status=status
            )

    async def update_project(
        self,
        project_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
    ) -> Project | None:
        _validate_status(status, PROJECT_STATUSES, "project")
        async with self._db.session() as sess:
            project = await ProjectRepository(sess).update(  # type: ignore[arg-type]
                project_id, name=name, description=description, status=status
            )
            if project is None:
                return None
            workspace_id = project.workspace_id
        action = "completed" if status == "completed" else "updated"
        await self._publish_project(project_id, workspace_id, action=action)
        return await self.get_project(project_id)

    async def delete_project(self, project_id: str) -> bool:
        """Deletes the project and **keeps its notes**, moving them back
        to the workspace.

        The ORM cascade would take them, which is the wrong default
        here: a note is a thought the user wrote down, and losing a
        batch of them as a side effect of tidying up a project is not a
        trade anyone would choose. Filing is reversible; deletion is
        not.
        """
        async with self._db.session() as sess:
            projects = ProjectRepository(sess)  # type: ignore[arg-type]
            project = await projects.get(project_id)
            if project is None:
                return False
            workspace_id = project.workspace_id
            detached = await projects.detach_notes(project_id)
            await projects.delete(project_id)
        if detached:
            _logger.info(
                "Project {} deleted; {} note(s) moved back to the workspace.",
                project_id,
                detached,
            )
        await self._publish_project(project_id, workspace_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Notes
    # ------------------------------------------------------------------
    async def create_note(
        self,
        workspace_id: str,
        title: str,
        *,
        content: str = "",
        project_id: str | None = None,
        content_format: str = "markdown",
    ) -> Note:
        title = (title or "").strip()
        if not title:
            raise ServiceError("Cannot create a note with an empty title.")
        _validate_status(content_format, NOTE_FORMATS, "note format")
        await self.require_workspace(workspace_id)
        if project_id is not None:
            project = await self.require_project(project_id)
            if project.workspace_id != workspace_id:
                raise ServiceError(
                    f"Project {project_id!r} belongs to a different workspace; "
                    "a note cannot span two."
                )

        async with self._db.session() as sess:
            note = await NoteRepository(sess).add(  # type: ignore[arg-type]
                workspace_id,
                title,
                content=content,
                project_id=project_id,
                content_format=content_format,
            )
            note_id = note.id
        await self._publish_note(note_id, workspace_id, project_id or "", action="created")
        return await self.require_note(note_id)

    async def get_note(self, note_id: str) -> Note | None:
        async with self._db.session() as sess:
            return await NoteRepository(sess).get(note_id)  # type: ignore[arg-type]

    async def require_note(self, note_id: str) -> Note:
        note = await self.get_note(note_id)
        if note is None:
            raise ServiceError(f"Note {note_id!r} does not exist.")
        return note

    async def list_notes(
        self, *, workspace_id: str | None = None, project_id: str | None = None
    ) -> list[Note]:
        async with self._db.session() as sess:
            return await NoteRepository(sess).list_notes(  # type: ignore[arg-type]
                workspace_id=workspace_id, project_id=project_id
            )

    async def update_note(
        self,
        note_id: str,
        *,
        title: str | None = None,
        content: str | None = None,
        content_format: str | None = None,
        project_id: str | None = None,
        pinned: bool | None = None,
        clear_project: bool = False,
    ) -> Note | None:
        _validate_status(content_format, NOTE_FORMATS, "note format")
        async with self._db.session() as sess:
            note = await NoteRepository(sess).update(  # type: ignore[arg-type]
                note_id,
                title=title,
                content=content,
                content_format=content_format,
                project_id=project_id,
                pinned=pinned,
                clear_project=clear_project,
            )
            if note is None:
                return None
            workspace_id, current_project = note.workspace_id, note.project_id or ""
        await self._publish_note(note_id, workspace_id, current_project, action="updated")
        return await self.get_note(note_id)

    async def delete_note(self, note_id: str) -> bool:
        async with self._db.session() as sess:
            notes = NoteRepository(sess)  # type: ignore[arg-type]
            note = await notes.get(note_id)
            if note is None:
                return False
            workspace_id, project_id = note.workspace_id, note.project_id or ""
            await notes.delete(note_id)
        await self._publish_note(note_id, workspace_id, project_id, action="deleted")
        return True

    # ------------------------------------------------------------------
    # Search hook
    # ------------------------------------------------------------------
    async def search_workspaces(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await WorkspaceRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=w.id,
                title=w.name,
                content=w.description,
                source="workspaces",
                score=1.0 if w.status == "active" else 0.5,
                uri=f"workspace://{w.id}",
                metadata={"status": w.status},
            )
            for w in hits
        ]

    async def search_projects(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await ProjectRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]
        return [
            SearchResult(
                id=p.id,
                title=p.name,
                content=p.description,
                source="projects",
                score=1.0 if p.status == "active" else 0.5,
                uri=f"project://{p.id}",
                metadata={"status": p.status, "workspace_id": p.workspace_id},
            )
            for p in hits
        ]

    async def search_notes(self, query: str, *, top_k: int = 10) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return []
        async with self._db.session() as sess:
            hits = await NoteRepository(sess).search(query, limit=top_k)  # type: ignore[arg-type]

        needle = query.lower()
        results: list[SearchResult] = []
        for note in hits:
            base = _NOTE_TITLE_SCORE if needle in note.title.lower() else _NOTE_CONTENT_SCORE
            score = base * (_PINNED_BOOST if note.pinned else 1.0)
            results.append(
                SearchResult(
                    id=note.id,
                    title=note.title,
                    content=note.content,
                    source="notes",
                    score=score,
                    uri=f"note://{note.id}",
                    metadata={
                        "workspace_id": note.workspace_id,
                        "project_id": note.project_id,
                        "pinned": note.pinned,
                    },
                )
            )
        return results

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    async def _publish_workspace(self, workspace_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import WorkspaceUpdatedEvent

        await self._event_bus.publish(
            WorkspaceUpdatedEvent(workspace_id=workspace_id, action=action)
        )

    async def _publish_project(self, project_id: str, workspace_id: str, *, action: str) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import ProjectUpdatedEvent

        await self._event_bus.publish(
            ProjectUpdatedEvent(project_id=project_id, workspace_id=workspace_id, action=action)
        )

    async def _publish_note(
        self, note_id: str, workspace_id: str, project_id: str, *, action: str
    ) -> None:
        if self._event_bus is None:
            return
        from jarvis.core.events.events import NoteUpdatedEvent

        await self._event_bus.publish(
            NoteUpdatedEvent(
                note_id=note_id,
                workspace_id=workspace_id,
                project_id=project_id,
                action=action,
            )
        )


def _validate_status(value: str | None, allowed: frozenset[str], label: str) -> None:
    if value is not None and value not in allowed:
        raise ServiceError(f"Unknown {label} {value!r}; allowed: {sorted(allowed)}.")


def _decode_settings(raw: str) -> WorkspaceSettings:
    """Malformed JSON yields defaults rather than raising -- settings are
    read on every workspace load, and one bad write must not make a
    workspace unopenable."""
    try:
        payload: Any = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return WorkspaceSettings()
    return WorkspaceSettings.from_dict(payload if isinstance(payload, dict) else {})
