"""File Platform end-to-end -- Milestone 11 Task Group C.

Real DI container, real REST app, real EventBus, real
``RuntimeWebSocketHub``, real files on a real disk. The unit tests prove
each piece; this proves they are wired to each other -- REST writes
reach WebSocket subscribers, the three new search sources joined the
*shared* registry, real bytes land inside the storage root and nowhere
else, and the Workspace substrate Task Group A shipped actually holds
this task group's data with foreign keys enforced.
"""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        test_client.storage_root = settings.resolved_files_dir  # type: ignore[attr-defined]
        test_client.tmp_path = tmp_path  # type: ignore[attr-defined]
        yield test_client

    container.runtime_ws_hub().stop()
    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _workspace(client, headers) -> str:
    return client.post("/api/v1/workspaces", json={"name": "W"}, headers=headers).json()["data"][
        "id"
    ]


def _file(client, headers, workspace_id: str, name: str, content: bytes = b"x", **extra) -> dict:
    body = {"workspace_id": workspace_id, "filename": name, "content_base64": _b64(content)}
    body.update(extra)
    return client.post("/api/v1/files", json=body, headers=headers).json()["data"]


def test_rest_writes_reach_a_real_websocket_subscriber(client, auth) -> None:
    """One EventBus, one relay -- not a second notification path bolted
    onto the file domain."""
    headers, token = auth
    workspace_id = _workspace(client, headers)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        folder_id = client.post(
            "/api/v1/folders",
            json={"workspace_id": workspace_id, "name": "Docs"},
            headers=headers,
        ).json()["data"]["id"]
        file_id = _file(client, headers, workspace_id, "a.md", b"# hi", folder_id=folder_id)["id"]
        client.post("/api/v1/attachments", json={"file_id": file_id}, headers=headers)

        received = [ws.receive_json() for _ in range(3)]

    assert [frame["type"] for frame in received] == [
        "folder.updated",
        "file.updated",
        "attachment.updated",
    ]
    assert received[0]["payload"]["relative_path"] == "Docs"
    assert received[1]["payload"]["folder_id"] == folder_id
    assert received[2]["payload"]["target"] == "workspace"


def test_the_three_sources_join_the_shared_search_service(client) -> None:
    """Registered through M10A's provider registry with no change to
    ``SearchService`` itself."""
    sources = {s.source_type for s in client.container.search_service().get_sources()}

    assert {"files", "folders", "attachments"} <= sources
    # Everything registered before is still there -- this is additive.
    assert {"workspaces", "projects", "notes"} <= sources
    assert {"tasks", "calendar", "reminders"} <= sources


def test_file_contents_are_findable_through_universal_search(client, auth) -> None:
    """The first source whose corpus is extracted document text rather
    than only stored fields."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Quantum"}, headers=headers
    )
    # The word appears only *inside* this file, never in its name.
    _file(client, headers, workspace_id, "notes.md", b"a quantum measurement")
    attached = _file(client, headers, workspace_id, "other.txt", b"unrelated")
    client.post(
        "/api/v1/attachments",
        json={"file_id": attached["id"], "caption": "quantum receipt"},
        headers=headers,
    )

    results = asyncio.run(client.container.search_service().search("quantum", top_k=30))

    assert {"files", "folders", "attachments"} <= {r.source for r in results}
    body_hit = next(r for r in results if r.source == "files")
    assert body_hit.title == "notes.md"


def test_bytes_land_inside_the_storage_root_and_nowhere_else(client, auth) -> None:
    """The containment guarantee, proved against the real filesystem
    rather than a returned path string."""
    headers, _ = auth
    root: Path = client.storage_root
    workspace_id = _workspace(client, headers)
    folder_id = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=headers
    ).json()["data"]["id"]
    _file(client, headers, workspace_id, "real.txt", b"payload", folder_id=folder_id)

    written = [p for p in root.rglob("*") if p.is_file()]
    assert [p.name for p in written] == ["real.txt"]
    assert written[0].read_bytes() == b"payload"
    # Every stored path is relative and workspace-first, never absolute.
    listed = client.get("/api/v1/files", headers=headers).json()["data"]
    assert listed[0]["relative_path"] == f"{workspace_id}/Docs/real.txt"
    assert not Path(listed[0]["relative_path"]).is_absolute()

    # And a traversal attempt writes nothing anywhere under tmp_path.
    before = sorted(p for p in client.tmp_path.rglob("*") if p.is_file())
    assert (
        client.post(
            "/api/v1/files",
            json={
                "workspace_id": workspace_id,
                "filename": "../../escaped.txt",
                "content_base64": _b64(b"nope"),
            },
            headers=headers,
        ).status_code
        == 400
    )
    after = sorted(p for p in client.tmp_path.rglob("*") if p.is_file())
    assert [p.name for p in after if p.name == "escaped.txt"] == []
    assert len(after) == len(before)


def test_file_data_hangs_off_the_workspace_substrate(client, auth) -> None:
    """Task Group A shipped the container precisely so C did not have to
    invent one: deleting the workspace takes folders, files and
    attachments with it, through real foreign keys."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    folder_id = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=headers
    ).json()["data"]["id"]
    file_id = _file(client, headers, workspace_id, "a.txt", folder_id=folder_id)["id"]
    attachment_id = client.post(
        "/api/v1/attachments", json={"file_id": file_id}, headers=headers
    ).json()["data"]["id"]

    assert client.delete(f"/api/v1/workspaces/{workspace_id}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/folders/{folder_id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/files/{file_id}", headers=headers).status_code == 404
    assert client.get(f"/api/v1/attachments/{attachment_id}", headers=headers).status_code == 404


def test_a_file_attached_to_a_task_survives_the_task_being_deleted(client, auth) -> None:
    """Deleting the *target* removes the link, not the document. The
    file is the user's; the attachment is only a statement about where
    it was used."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    task_id = client.post(
        "/api/v1/tasks", json={"workspace_id": workspace_id, "title": "T"}, headers=headers
    ).json()["data"]["id"]
    file_id = _file(client, headers, workspace_id, "brief.txt", b"content")["id"]
    client.post(
        "/api/v1/attachments",
        json={"file_id": file_id, "target": "task", "target_id": task_id},
        headers=headers,
    )

    assert client.delete(f"/api/v1/tasks/{task_id}", headers=headers).status_code == 204

    assert client.get(f"/api/v1/files/{file_id}", headers=headers).status_code == 200
    content = client.get(f"/api/v1/files/{file_id}/content", headers=headers).json()["data"]
    assert base64.b64decode(content["content_base64"]) == b"content"
    # The dangling link is gone -- that is what the cascade is for.
    assert client.get("/api/v1/attachments", headers=headers).json()["meta"]["count"] == 0


def test_attaching_to_a_nonexistent_target_cannot_create_a_dangling_row(client, auth) -> None:
    """Foreign keys are enforced, so a fabricated parent id is rejected
    by the database rather than stored and discovered later."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    file_id = _file(client, headers, workspace_id, "a.txt")["id"]

    response = client.post(
        "/api/v1/attachments",
        json={"file_id": file_id, "target": "task", "target_id": "does-not-exist"},
        headers=headers,
    )

    assert response.status_code >= 400
    assert client.get("/api/v1/attachments", headers=headers).json()["meta"]["count"] == 0


def test_a_file_moves_with_its_folder_end_to_end(client, auth) -> None:
    headers, _ = auth
    root: Path = client.storage_root
    workspace_id = _workspace(client, headers)
    source = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Src"}, headers=headers
    ).json()["data"]["id"]
    destination = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Dst"}, headers=headers
    ).json()["data"]["id"]
    file_id = _file(client, headers, workspace_id, "a.txt", b"payload", folder_id=source)["id"]

    moved = client.patch(
        f"/api/v1/folders/{source}/parent",
        json={"parent_folder_id": destination},
        headers=headers,
    )
    assert moved.json()["data"]["relative_path"] == "Dst/Src"
    assert moved.json()["meta"]["moved"] is True

    refreshed = client.get(f"/api/v1/files/{file_id}", headers=headers).json()["data"]
    assert refreshed["relative_path"] == f"{workspace_id}/Dst/Src/a.txt"
    assert (root / workspace_id / "Dst" / "Src" / "a.txt").read_bytes() == b"payload"
    assert not (root / workspace_id / "Src").exists()


def test_di_exposes_one_singleton_per_service_and_manager(client) -> None:
    container = client.container

    for name in (
        "folder_service",
        "file_service",
        "attachment_service",
        "folder_manager",
        "file_manager",
        "attachment_manager",
    ):
        provider = getattr(container, name)
        assert provider() is provider(), name


def test_the_storage_root_follows_the_data_directory(client) -> None:
    """Derived rather than stored, so relocating ``data_dir`` moves the
    file root with it instead of leaving it behind."""
    settings = client.container.settings()

    assert settings.files.storage_dir is None
    assert settings.resolved_files_dir == settings.resolved_data_dir / "files"
    assert client.storage_root == settings.resolved_files_dir
