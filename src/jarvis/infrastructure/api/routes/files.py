"""File Platform API -- Milestone 11 Task Group C.

``/api/v1/files``, ``/api/v1/folders`` and ``/api/v1/attachments`` --
thin REST over ``FileService`` / ``FolderService`` /
``AttachmentService``, plus the composed reads their managers provide.
Same ``Depends(get_current_session)`` Bearer auth and ``{data, meta}``
envelope as every resource router since M9 Task Group E; this one owns
no state and no logic of its own.

One module for three prefixes, mirroring ``workspaces.py`` and
``productivity.py``: they ship together and share every convention.

**Why file bytes travel as base64 inside the envelope.** Multipart
uploads would need ``python-multipart``, which this project does not
declare as a dependency -- it is present only transitively, and building
a shipped endpoint on an undeclared package is a break waiting for
someone else's lockfile. Base64 also keeps every response in this API
the same ``{data, meta}`` shape, so one client parser handles all of it.
The cost is a third more bytes on the wire for a local API; the payload
ceiling is ``JARVIS_FILES_MAX_UPLOAD_BYTES`` and it is enforced here
rather than being left to the storage layer to discover.

**Paths are never accepted from the caller.** A request names a folder
by id, and the service derives the path. There is no endpoint that takes
a path fragment, which is the simplest possible defence against
traversal: the class of input that could escape the storage root is not
part of the API surface at all.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from jarvis.infrastructure.api.auth import Envelope, envelope, get_current_session

if TYPE_CHECKING:
    from jarvis.services.file_managers import (
        AttachmentManager,
        FileManager,
        FolderManager,
    )
    from jarvis.services.file_service import (
        AttachmentService,
        FileService,
        FolderService,
    )

router = APIRouter(tags=["files"], dependencies=[Depends(get_current_session)])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------
class CreateFolderRequest(BaseModel):
    workspace_id: str
    name: str
    parent_folder_id: str | None = None


class RenameFolderRequest(BaseModel):
    name: str


class MoveFolderRequest(BaseModel):
    """``parent_folder_id: null`` moves the folder to the workspace
    root, which is a real destination rather than a missing value."""

    parent_folder_id: str | None = None


class CreateFileRequest(BaseModel):
    workspace_id: str
    filename: str
    content_base64: str = ""
    folder_id: str | None = None
    project_id: str | None = None
    description: str = ""
    tags: list[str] = []


class UpdateFileRequest(BaseModel):
    description: str | None = None
    project_id: str | None = None
    clear_project: bool = False


class RenameFileRequest(BaseModel):
    filename: str


class MoveFileRequest(BaseModel):
    folder_id: str | None = None


class TagRequest(BaseModel):
    tag: str


class MetadataRequest(BaseModel):
    key: str
    value: str = ""


class AttachRequest(BaseModel):
    file_id: str
    target: str = "workspace"
    target_id: str | None = None
    caption: str = ""


# ---------------------------------------------------------------------------
# Resolution + serialization
# ---------------------------------------------------------------------------
def _files(request: Request) -> FileService:
    return cast("FileService", request.app.state.container.file_service())


def _folders(request: Request) -> FolderService:
    return cast("FolderService", request.app.state.container.folder_service())


def _attachments(request: Request) -> AttachmentService:
    return cast("AttachmentService", request.app.state.container.attachment_service())


def _file_manager(request: Request) -> FileManager:
    return cast("FileManager", request.app.state.container.file_manager())


def _folder_manager(request: Request) -> FolderManager:
    return cast("FolderManager", request.app.state.container.folder_manager())


def _attachment_manager(request: Request) -> AttachmentManager:
    return cast("AttachmentManager", request.app.state.container.attachment_manager())


def _max_upload_bytes(request: Request) -> int:
    settings = request.app.state.container.settings()
    return int(settings.files.max_upload_bytes)


def _iso(moment: Any) -> str | None:
    return moment.isoformat() if moment else None


def _folder_payload(folder: Any) -> dict[str, Any]:
    return {
        "id": folder.id,
        "workspace_id": folder.workspace_id,
        "parent_folder_id": folder.parent_folder_id,
        "name": folder.name,
        "relative_path": folder.relative_path,
        "created_at": _iso(folder.created_at),
        "updated_at": _iso(folder.updated_at),
    }


def _file_payload(file: Any) -> dict[str, Any]:
    """No ``content`` key. A listing that inlined every file's bytes
    would make ``GET /files`` unbounded; content has its own endpoint."""
    return {
        "id": file.id,
        "workspace_id": file.workspace_id,
        "folder_id": file.folder_id,
        "project_id": file.project_id,
        "filename": file.filename,
        "relative_path": file.relative_path,
        "extension": file.extension,
        "mime_type": file.mime_type,
        "size_bytes": file.size_bytes,
        "description": file.description,
        "created_at": _iso(file.created_at),
        "updated_at": _iso(file.updated_at),
    }


def _attachment_payload(attachment: Any) -> dict[str, Any]:
    from jarvis.services.file_service import describe_target

    target, target_id = describe_target(attachment)
    return {
        "id": attachment.id,
        "workspace_id": attachment.workspace_id,
        "file_id": attachment.file_id,
        "target": target,
        "target_id": target_id,
        "caption": attachment.caption,
        "created_at": _iso(attachment.created_at),
    }


def _index_payload(record: Any) -> dict[str, Any]:
    if record is None:
        return {"status": "unindexed", "detail": "", "indexed_at": None, "characters": 0}
    return {
        "status": record.status,
        "detail": record.detail,
        "indexed_at": _iso(record.indexed_at),
        "characters": len(record.content_text),
    }


def _bad_request(err: Exception) -> HTTPException:
    """A ``ServiceError`` means the caller asked for something invalid --
    a name containing ``..``, a folder in another workspace, a duplicate
    filename. 400, not 500: nothing broke."""
    return HTTPException(status_code=400, detail=str(err))


def _decode(content_base64: str, limit: int) -> bytes:
    """Decodes and size-checks in one place.

    ``validate=True`` so malformed base64 is a 400 rather than silently
    decoding to whatever survived -- a caller with a broken encoder
    should hear about it, not get a corrupt file stored under the name
    they chose.
    """
    try:
        content = base64.b64decode(content_base64 or "", validate=True)
    except (binascii.Error, ValueError) as err:
        raise HTTPException(
            status_code=400, detail=f"content_base64 is not valid base64: {err}"
        ) from err
    if len(content) > limit:
        raise HTTPException(
            status_code=413,
            detail=f"File is {len(content)} bytes; the limit is {limit}.",
        )
    return content


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
@router.post("/folders", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_folder(body: CreateFolderRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        folder = await _folders(request).create_folder(
            body.workspace_id, body.name, parent_folder_id=body.parent_folder_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_folder_payload(folder), meta={"created": True})


@router.get("/folders", response_model=Envelope[list[dict[str, Any]]])
async def list_folders(
    request: Request,
    workspace_id: str | None = None,
    parent_folder_id: str | None = None,
    root_only: bool = False,
) -> Envelope[list[dict[str, Any]]]:
    folders = await _folders(request).list_folders(
        workspace_id=workspace_id, parent_folder_id=parent_folder_id, root_only=root_only
    )
    return envelope([_folder_payload(folder) for folder in folders], meta={"count": len(folders)})


@router.get("/folders/tree", response_model=Envelope[dict[str, Any]])
async def folder_tree(request: Request, workspace_id: str) -> Envelope[dict[str, Any]]:
    """Declared before ``/folders/{folder_id}`` on purpose -- FastAPI
    matches in declaration order, so a literal segment must come first
    or ``tree`` would be read as an id."""
    from jarvis.core.exceptions import ServiceError

    try:
        tree = await _folder_manager(request).tree(workspace_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(tree, meta={"workspace_id": workspace_id})


@router.get("/folders/{folder_id}", response_model=Envelope[dict[str, Any]])
async def get_folder(folder_id: str, request: Request) -> Envelope[dict[str, Any]]:
    folder = await _folders(request).get_folder(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id!r} not found.")
    return envelope(_folder_payload(folder))


@router.get("/folders/{folder_id}/contents", response_model=Envelope[dict[str, Any]])
async def folder_contents(folder_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        contents = await _folder_manager(request).contents(folder_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(contents)


@router.patch("/folders/{folder_id}/name", response_model=Envelope[dict[str, Any]])
async def rename_folder(
    folder_id: str, body: RenameFolderRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        folder = await _folders(request).rename_folder(folder_id, body.name)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_folder_payload(folder), meta={"renamed": True})


@router.patch("/folders/{folder_id}/parent", response_model=Envelope[dict[str, Any]])
async def move_folder(
    folder_id: str, body: MoveFolderRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        folder = await _folders(request).move_folder(
            folder_id, parent_folder_id=body.parent_folder_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_folder_payload(folder), meta={"moved": True})


@router.delete("/folders/{folder_id}", response_model=Envelope[dict[str, Any]])
async def delete_folder(
    folder_id: str, request: Request, recursive: bool = False
) -> Envelope[dict[str, Any]]:
    """``recursive`` defaults to false, so deleting a non-empty folder is
    a 400 explaining what is inside it rather than a silent cascade over
    real files."""
    from jarvis.core.exceptions import ServiceError

    try:
        deleted = await _folders(request).delete_folder(folder_id, recursive=recursive)
    except ServiceError as err:
        raise _bad_request(err) from err
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Folder {folder_id!r} not found.")
    return envelope({"id": folder_id, "deleted": True}, meta={"recursive": recursive})


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------
@router.post("/files", response_model=Envelope[dict[str, Any]], status_code=201)
async def create_file(body: CreateFileRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    content = _decode(body.content_base64, _max_upload_bytes(request))
    try:
        file = await _files(request).create_file(
            body.workspace_id,
            body.filename,
            content,
            folder_id=body.folder_id,
            project_id=body.project_id,
            description=body.description,
            tags=body.tags,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_file_payload(file), meta={"created": True, "size_bytes": len(content)})


@router.get("/files", response_model=Envelope[list[dict[str, Any]]])
async def list_files(
    request: Request,
    workspace_id: str | None = None,
    folder_id: str | None = None,
    project_id: str | None = None,
    extension: str | None = None,
    tag: str | None = None,
    unfiled_only: bool = False,
) -> Envelope[list[dict[str, Any]]]:
    files = await _files(request).list_files(
        workspace_id=workspace_id,
        folder_id=folder_id,
        project_id=project_id,
        extension=extension,
        tag=tag,
        unfiled_only=unfiled_only,
    )
    return envelope([_file_payload(file) for file in files], meta={"count": len(files)})


@router.get("/files/stats", response_model=Envelope[dict[str, Any]])
async def file_stats(request: Request, workspace_id: str) -> Envelope[dict[str, Any]]:
    return envelope(await _file_manager(request).overview(workspace_id))


@router.get("/files/{file_id}", response_model=Envelope[dict[str, Any]])
async def get_file(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    file = await _files(request).get_file(file_id)
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id!r} not found.")
    return envelope(_file_payload(file))


@router.get("/files/{file_id}/content", response_model=Envelope[dict[str, Any]])
async def read_file(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """The bytes, base64-encoded, with the MIME type so a client knows
    what it received without re-deriving it from the name."""
    from jarvis.core.exceptions import ServiceError

    try:
        file = await _files(request).require_file(file_id)
        content = await _files(request).read_file(file_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(
        {
            "id": file_id,
            "filename": file.filename,
            "mime_type": file.mime_type,
            "size_bytes": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }
    )


@router.get("/files/{file_id}/context", response_model=Envelope[dict[str, Any]])
async def file_context(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        context = await _file_manager(request).context(file_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(context)


@router.patch("/files/{file_id}", response_model=Envelope[dict[str, Any]])
async def update_file(
    file_id: str, body: UpdateFileRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        file = await _files(request).update_file(
            file_id,
            description=body.description,
            project_id=body.project_id,
            clear_project=body.clear_project,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    if file is None:
        raise HTTPException(status_code=404, detail=f"File {file_id!r} not found.")
    return envelope(_file_payload(file), meta={"updated": True})


@router.patch("/files/{file_id}/name", response_model=Envelope[dict[str, Any]])
async def rename_file(
    file_id: str, body: RenameFileRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        file = await _files(request).rename_file(file_id, body.filename)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_file_payload(file), meta={"renamed": True})


@router.patch("/files/{file_id}/folder", response_model=Envelope[dict[str, Any]])
async def move_file(
    file_id: str, body: MoveFileRequest, request: Request
) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        file = await _files(request).move_file(file_id, folder_id=body.folder_id)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_file_payload(file), meta={"moved": True})


@router.delete("/files/{file_id}", response_model=Envelope[dict[str, Any]])
async def delete_file(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    deleted = await _files(request).delete_file(file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File {file_id!r} not found.")
    return envelope({"id": file_id, "deleted": True})


# ---- Tags, metadata, indexing ---------------------------------------------
@router.get("/files/{file_id}/tags", response_model=Envelope[list[str]])
async def list_file_tags(file_id: str, request: Request) -> Envelope[list[str]]:
    tags = await _files(request).tags_for(file_id)
    return envelope(tags, meta={"count": len(tags)})


@router.post("/files/{file_id}/tags", response_model=Envelope[list[str]], status_code=201)
async def add_file_tag(file_id: str, body: TagRequest, request: Request) -> Envelope[list[str]]:
    from jarvis.core.exceptions import ServiceError

    try:
        tags = await _files(request).add_tag(file_id, body.tag)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(tags, meta={"count": len(tags)})


@router.delete("/files/{file_id}/tags/{tag}", response_model=Envelope[list[str]])
async def remove_file_tag(file_id: str, tag: str, request: Request) -> Envelope[list[str]]:
    tags = await _files(request).remove_tag(file_id, tag)
    return envelope(tags, meta={"count": len(tags)})


@router.get("/files/{file_id}/metadata", response_model=Envelope[dict[str, str]])
async def list_file_metadata(file_id: str, request: Request) -> Envelope[dict[str, str]]:
    rows = await _files(request).list_metadata(file_id)
    return envelope({row.key: row.value for row in rows}, meta={"count": len(rows)})


@router.put("/files/{file_id}/metadata", response_model=Envelope[dict[str, str]])
async def set_file_metadata(
    file_id: str, body: MetadataRequest, request: Request
) -> Envelope[dict[str, str]]:
    from jarvis.core.exceptions import ServiceError

    try:
        row = await _files(request).set_metadata(file_id, body.key, body.value)
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope({row.key: row.value}, meta={"updated": True})


@router.delete("/files/{file_id}/metadata/{key}", response_model=Envelope[dict[str, Any]])
async def delete_file_metadata(
    file_id: str, key: str, request: Request
) -> Envelope[dict[str, Any]]:
    deleted = await _files(request).delete_metadata(file_id, key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Metadata key {key!r} not found.")
    return envelope({"file_id": file_id, "key": key, "deleted": True})


@router.get("/files/{file_id}/index", response_model=Envelope[dict[str, Any]])
async def get_file_index(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    return envelope(_index_payload(await _files(request).index_record(file_id)))


@router.post("/files/{file_id}/index", response_model=Envelope[dict[str, Any]])
async def reindex_file(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        record = await _files(request).reindex_file(file_id)
    except ServiceError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return envelope(_index_payload(record), meta={"reindexed": True})


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------
@router.post("/attachments", response_model=Envelope[dict[str, Any]], status_code=201)
async def attach_file(body: AttachRequest, request: Request) -> Envelope[dict[str, Any]]:
    from jarvis.core.exceptions import ServiceError

    try:
        attachment = await _attachments(request).attach(
            body.file_id,
            target=body.target,
            target_id=body.target_id,
            caption=body.caption,
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(_attachment_payload(attachment), meta={"attached": True})


@router.get("/attachments", response_model=Envelope[list[dict[str, Any]]])
async def list_attachments(
    request: Request,
    workspace_id: str | None = None,
    file_id: str | None = None,
    target: str | None = None,
    target_id: str | None = None,
) -> Envelope[list[dict[str, Any]]]:
    from jarvis.core.exceptions import ServiceError

    try:
        attachments = await _attachments(request).list_attachments(
            workspace_id=workspace_id, file_id=file_id, target=target, target_id=target_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(
        [_attachment_payload(attachment) for attachment in attachments],
        meta={"count": len(attachments)},
    )


@router.get("/attachments/for-target", response_model=Envelope[dict[str, Any]])
async def attachments_for_target(
    request: Request,
    target: str,
    target_id: str,
    workspace_id: str | None = None,
) -> Envelope[dict[str, Any]]:
    """The composed view: every attachment on one entity, each with its
    file resolved. Declared before ``/{attachment_id}`` so the literal
    segment wins."""
    from jarvis.core.exceptions import ServiceError

    try:
        payload = await _attachment_manager(request).for_target(
            target, target_id, workspace_id=workspace_id
        )
    except ServiceError as err:
        raise _bad_request(err) from err
    return envelope(payload)


@router.get("/attachments/for-file/{file_id}", response_model=Envelope[dict[str, Any]])
async def attachments_for_file(file_id: str, request: Request) -> Envelope[dict[str, Any]]:
    return envelope(await _attachment_manager(request).for_file(file_id))


@router.get("/attachments/{attachment_id}", response_model=Envelope[dict[str, Any]])
async def get_attachment(attachment_id: str, request: Request) -> Envelope[dict[str, Any]]:
    attachment = await _attachments(request).get_attachment(attachment_id)
    if attachment is None:
        raise HTTPException(status_code=404, detail=f"Attachment {attachment_id!r} not found.")
    return envelope(_attachment_payload(attachment))


@router.delete("/attachments/{attachment_id}", response_model=Envelope[dict[str, Any]])
async def detach_file(attachment_id: str, request: Request) -> Envelope[dict[str, Any]]:
    """Removes the link. **The file is untouched** -- detaching is not
    deleting, and conflating the two would make "this does not belong on
    that task" destroy the document."""
    detached = await _attachments(request).detach(attachment_id)
    if not detached:
        raise HTTPException(status_code=404, detail=f"Attachment {attachment_id!r} not found.")
    return envelope({"id": attachment_id, "detached": True, "file_deleted": False})
