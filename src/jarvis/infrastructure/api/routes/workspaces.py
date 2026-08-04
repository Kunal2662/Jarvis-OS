"""Workspace API -- Milestone 11 Task Group A.

``/api/v1/workspaces``, ``/api/v1/projects`` and ``/api/v1/notes`` --
thin REST over ``WorkspaceService``, plus two composed reads served by
``WorkspaceManager``. Same ``Depends(get_current_session)`` Bearer auth
and ``{data, meta}`` envelope every resource router since M9 Task Group
E uses; this one owns no state and no logic of its own.

**CRUD only, deliberately.** No collaboration, no sharing, no
synchronization -- those need an identity model and a conflict story
this milestone has not built, and stubbing endpoints for them would
advertise capability that does not exist.

Three top-level prefixes rather than nesting projects and notes under
``/workspaces/{id}/``: a note is addressable on its own (the Command
Palette will link straight to one), and a caller that has an id should
not need its parent's to fetch it. Filtering by parent is a query
parameter on the collection, which gives both access patterns without
two route trees.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.workspace_manager import WorkspaceManager
    from jarvis.services.workspace_service import WorkspaceService

router = APIRouter(tags=["workspaces"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class CreateWorkspaceRequest(BaseModel):
    name: str
    description: str = ""


class UpdateWorkspaceRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class CreateProjectRequest(BaseModel):
    workspace_id: str
    name: str
    description: str = ""


class UpdateProjectRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None


class CreateNoteRequest(BaseModel):
    workspace_id: str
    title: str
    content: str = ""
    project_id: str | None = None
    content_format: str = "markdown"


class UpdateNoteRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    content_format: str | None = None
    project_id: str | None = None
    pinned: bool | None = None
    #: Distinct from ``project_id=None``, which means "leave alone" --
    #: see ``NoteRepository.update``.
    clear_project: bool = False


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _workspaces(request: Request) -> WorkspaceService:
    return cast("WorkspaceService", request.app.state.container.workspace_service())


def _manager(request: Request) -> WorkspaceManager:
    return cast("WorkspaceManager", request.app.state.container.workspace_manager())


def _workspace_payload(workspace: Any) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "name": workspace.name,
        "description": workspace.description,
        "status": workspace.status,
        "created_at": workspace.created_at.isoformat() if workspace.created_at else None,
        "updated_at": workspace.updated_at.isoformat() if workspace.updated_at else None,
    }


def _project_payload(project: Any) -> dict[str, Any]:
    return {
        "id": project.id,
        "workspace_id": project.workspace_id,
        "name": project.name,
        "description": project.description,
        "status": project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _note_payload(note: Any) -> dict[str, Any]:
    return {
        "id": note.id,
        "workspace_id": note.workspace_id,
        "project_id": note.project_id,
        "title": note.title,
        "content": note.content,
        "content_format": note.content_format,
        "pinned": note.pinned,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    }


def _bad_request(err: Exception) -> HTTPException:
    """``ServiceError`` means the caller asked for something invalid --
    an empty name, an unknown status, a cross-workspace note. 400, not
    500: nothing broke."""
    return HTTPException(status_code=400, detail=str(err))


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------
@router.post("/workspaces", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_workspace(
    body: CreateWorkspaceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        workspace = await _workspaces(request).create_workspace(
            body.name, description=body.description
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_workspace_payload(workspace), meta={"created": True})


@router.get("/workspaces", response_model=Envelope[list[dict[str, Any]]])
async def list_workspaces(
    request: Request, status: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        workspaces = await _workspaces(request).list_workspaces(status=status)
    except ServiceError as err:
        raise _bad_request(err) from err
    payload = [_workspace_payload(w) for w in workspaces]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/workspaces/{workspace_id}", response_model=Envelope[dict[str, Any]])
async def get_workspace(workspace_id: str, request: Request) -> Envelope[dict[str, Any]]:
    workspace = await _workspaces(request).get_workspace(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return envelope(_workspace_payload(workspace))


@router.get("/workspaces/{workspace_id}/metadata", response_model=Envelope[dict[str, Any]])
async def workspace_metadata(workspace_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Derived counts and last activity -- computed on read, never
    stored. See ``domain/workspace/models.py``."""
    from jarvis.core.exceptions import ServiceError

    try:
        metadata = await _workspaces(request).metadata(workspace_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(metadata.as_dict())


@router.get("/workspaces/{workspace_id}/overview", response_model=Envelope[dict[str, Any]])
async def workspace_overview(workspace_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Workspace + projects + notes + metadata in one call, via
    ``WorkspaceManager`` -- the four reads a client would otherwise
    make in sequence."""
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _manager(request).overview(workspace_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.get("/workspaces/{workspace_id}/context", response_model=Envelope[dict[str, Any]])
async def workspace_context(workspace_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """The overview plus what Knowledge and Memory relate to it. Task
    Group D extends this; the shape is additive."""
    from jarvis.core.exceptions import ServiceError

    try:
        return envelope(await _manager(request).context(workspace_id))
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err


@router.patch("/workspaces/{workspace_id}", response_model=Envelope[dict[str, Any]])
async def update_workspace(
    workspace_id: str, body: UpdateWorkspaceRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        workspace = await _workspaces(request).update_workspace(
            workspace_id, name=body.name, description=body.description, status=body.status
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return envelope(_workspace_payload(workspace))


@router.delete("/workspaces/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: str, request: Request) -> None:
    if not await _workspaces(request).delete_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="Workspace not found.")


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@router.post("/projects", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_project(body: CreateProjectRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        project = await _workspaces(request).create_project(
            body.workspace_id, body.name, description=body.description
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_project_payload(project), meta={"created": True})


@router.get("/projects", response_model=Envelope[list[dict[str, Any]]])
async def list_projects(
    request: Request, workspace_id: str | None = None, status: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        projects = await _workspaces(request).list_projects(
            workspace_id=workspace_id, status=status
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    payload = [_project_payload(p) for p in projects]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/projects/{project_id}", response_model=Envelope[dict[str, Any]])
async def get_project(project_id: str, request: Request) -> Envelope[dict[str, Any]]:
    project = await _workspaces(request).get_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return envelope(_project_payload(project))


@router.patch("/projects/{project_id}", response_model=Envelope[dict[str, Any]])
async def update_project(
    project_id: str, body: UpdateProjectRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        project = await _workspaces(request).update_project(
            project_id, name=body.name, description=body.description, status=body.status
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found.")
    return envelope(_project_payload(project))


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: str, request: Request) -> None:
    """Deletes the project; its notes move back to the workspace rather
    than being cascaded away -- see ``WorkspaceService.delete_project``."""
    if not await _workspaces(request).delete_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found.")


# ---------------------------------------------------------------------------
# Notes
# ---------------------------------------------------------------------------
@router.post("/notes", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_note(body: CreateNoteRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        note = await _workspaces(request).create_note(
            body.workspace_id,
            body.title,
            content=body.content,
            project_id=body.project_id,
            content_format=body.content_format,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_note_payload(note), meta={"created": True})


@router.get("/notes", response_model=Envelope[list[dict[str, Any]]])
async def list_notes(
    request: Request, workspace_id: str | None = None, project_id: str | None = None
) -> Envelope[list[dict[str, Any]]]:
    notes = await _workspaces(request).list_notes(workspace_id=workspace_id, project_id=project_id)
    payload = [_note_payload(n) for n in notes]
    return envelope(payload, meta={"count": len(payload)})


@router.get("/notes/{note_id}", response_model=Envelope[dict[str, Any]])
async def get_note(note_id: str, request: Request) -> Envelope[dict[str, Any]]:
    note = await _workspaces(request).get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    return envelope(_note_payload(note))


@router.patch("/notes/{note_id}", response_model=Envelope[dict[str, Any]])
async def update_note(
    note_id: str, body: UpdateNoteRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        note = await _workspaces(request).update_note(
            note_id,
            title=body.title,
            content=body.content,
            content_format=body.content_format,
            project_id=body.project_id,
            pinned=body.pinned,
            clear_project=body.clear_project,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found.")
    return envelope(_note_payload(note))


@router.delete("/notes/{note_id}", status_code=204)
async def delete_note(note_id: str, request: Request) -> None:
    if not await _workspaces(request).delete_note(note_id):
        raise HTTPException(status_code=404, detail="Note not found.")
