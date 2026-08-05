"""File Platform REST tests -- Milestone 11 Task Group C.

Against the real FastAPI app and the real DI container, matching
``test_productivity_route.py``. The storage root follows ``data_dir``,
so every test gets its own directory under ``tmp_path`` and nothing here
touches a real user's files.
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
    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        test_client.storage_root = settings.resolved_files_dir  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


@pytest.fixture
def workspace_id(client, auth) -> str:
    return client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth).json()["data"]["id"]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _create_file(client, auth, workspace_id: str, name: str, content: bytes = b"x", **extra):
    body = {"workspace_id": workspace_id, "filename": name, "content_base64": _b64(content)}
    body.update(extra)
    return client.post("/api/v1/files", json=body, headers=auth)


# --- Auth + envelope ------------------------------------------------------------


def test_every_collection_requires_a_session(client) -> None:
    for path in ("/api/v1/files", "/api/v1/folders", "/api/v1/attachments"):
        assert client.get(path).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, workspace_id) -> None:
    created = _create_file(client, auth, workspace_id, "a.txt")
    listed = client.get("/api/v1/files", headers=auth)

    for response in (created, listed):
        assert set(response.json()) == {"data", "meta"}
    assert created.json()["meta"]["created"] is True
    assert listed.json()["meta"]["count"] == 1


# --- Folders --------------------------------------------------------------------


def test_folder_crud_round_trip(client, auth, workspace_id) -> None:
    created = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=auth
    )
    assert created.status_code == 201
    folder_id = created.json()["data"]["id"]
    assert created.json()["data"]["relative_path"] == "Docs"

    child = client.post(
        "/api/v1/folders",
        json={"workspace_id": workspace_id, "name": "2026", "parent_folder_id": folder_id},
        headers=auth,
    ).json()["data"]
    assert child["relative_path"] == "Docs/2026"

    renamed = client.patch(
        f"/api/v1/folders/{folder_id}/name", json={"name": "Papers"}, headers=auth
    )
    assert renamed.json()["data"]["relative_path"] == "Papers"

    moved = client.patch(
        f"/api/v1/folders/{child['id']}/parent",
        json={"parent_folder_id": None},
        headers=auth,
    )
    assert moved.json()["data"]["relative_path"] == "2026"

    assert client.delete(f"/api/v1/folders/{folder_id}", headers=auth).status_code == 200
    assert client.get(f"/api/v1/folders/{folder_id}", headers=auth).status_code == 404


def test_deleting_a_non_empty_folder_needs_recursive(client, auth, workspace_id) -> None:
    folder_id = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=auth
    ).json()["data"]["id"]
    _create_file(client, auth, workspace_id, "a.txt", folder_id=folder_id)

    refused = client.delete(f"/api/v1/folders/{folder_id}", headers=auth)
    assert refused.status_code == 400
    assert "not empty" in refused.json()["detail"]

    ok = client.delete(f"/api/v1/folders/{folder_id}?recursive=true", headers=auth)
    assert ok.status_code == 200
    assert ok.json()["meta"]["recursive"] is True


def test_tree_route_is_not_shadowed_by_the_id_route(client, auth, workspace_id) -> None:
    """``/folders/tree`` is declared before ``/folders/{folder_id}``, so
    the literal segment wins -- the classic FastAPI ordering trap."""
    client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=auth
    )
    _create_file(client, auth, workspace_id, "loose.txt")

    tree = client.get(f"/api/v1/folders/tree?workspace_id={workspace_id}", headers=auth)
    assert tree.status_code == 200
    payload = tree.json()["data"]
    assert payload["folder_count"] == 1
    assert [f["filename"] for f in payload["unfiled_files"]] == ["loose.txt"]


def test_folder_contents_lists_one_level(client, auth, workspace_id) -> None:
    parent = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "A"}, headers=auth
    ).json()["data"]["id"]
    client.post(
        "/api/v1/folders",
        json={"workspace_id": workspace_id, "name": "B", "parent_folder_id": parent},
        headers=auth,
    )
    _create_file(client, auth, workspace_id, "a.txt", folder_id=parent)

    contents = client.get(f"/api/v1/folders/{parent}/contents", headers=auth).json()["data"]
    assert [f["name"] for f in contents["subfolders"]] == ["B"]
    assert [f["filename"] for f in contents["files"]] == ["a.txt"]


# --- Files ----------------------------------------------------------------------


def test_file_crud_round_trip(client, auth, workspace_id) -> None:
    created = _create_file(client, auth, workspace_id, "notes.md", b"# Title")
    assert created.status_code == 201
    file_id = created.json()["data"]["id"]
    assert created.json()["data"]["extension"] == ".md"
    assert created.json()["meta"]["size_bytes"] == 7

    content = client.get(f"/api/v1/files/{file_id}/content", headers=auth).json()["data"]
    assert base64.b64decode(content["content_base64"]) == b"# Title"

    patched = client.patch(f"/api/v1/files/{file_id}", json={"description": "A note"}, headers=auth)
    assert patched.json()["data"]["description"] == "A note"

    renamed = client.patch(
        f"/api/v1/files/{file_id}/name", json={"filename": "renamed.md"}, headers=auth
    )
    assert renamed.json()["data"]["filename"] == "renamed.md"

    assert client.delete(f"/api/v1/files/{file_id}", headers=auth).status_code == 200
    assert client.get(f"/api/v1/files/{file_id}", headers=auth).status_code == 404


def test_a_listing_never_inlines_file_bytes(client, auth, workspace_id) -> None:
    """``GET /files`` would be unbounded if it carried content."""
    _create_file(client, auth, workspace_id, "a.txt", b"secret-bytes")

    raw = client.get("/api/v1/files", headers=auth).text
    assert "secret-bytes" not in raw
    assert "content_base64" not in raw


def test_a_traversal_filename_is_refused_and_writes_nothing(client, auth, workspace_id) -> None:
    """The property that matters most: no caller-supplied name can put
    bytes outside the storage root."""
    root: Path = client.storage_root
    for name in ("../escape.txt", "..", "a/b.txt", "a\\b.txt", "con.txt"):
        response = _create_file(client, auth, workspace_id, name, b"payload")
        assert response.status_code == 400, name

    assert not (root.parent / "escape.txt").exists()
    assert client.get("/api/v1/files", headers=auth).json()["meta"]["count"] == 0


def test_malformed_base64_is_a_400_not_a_corrupt_file(client, auth, workspace_id) -> None:
    response = client.post(
        "/api/v1/files",
        json={"workspace_id": workspace_id, "filename": "a.txt", "content_base64": "not!base64"},
        headers=auth,
    )
    assert response.status_code == 400
    assert "base64" in response.json()["detail"]
    assert client.get("/api/v1/files", headers=auth).json()["meta"]["count"] == 0


def test_an_oversized_upload_is_refused_with_413(client, auth, workspace_id) -> None:
    settings = client.container.settings()
    settings.files.max_upload_bytes = 4

    response = _create_file(client, auth, workspace_id, "a.txt", b"more than four bytes")
    assert response.status_code == 413
    assert "limit is 4" in response.json()["detail"]


def test_filtering_a_listing(client, auth, workspace_id) -> None:
    folder_id = client.post(
        "/api/v1/folders", json={"workspace_id": workspace_id, "name": "Docs"}, headers=auth
    ).json()["data"]["id"]
    _create_file(client, auth, workspace_id, "a.md", folder_id=folder_id, tags=["work"])
    _create_file(client, auth, workspace_id, "b.txt", tags=["homework"])

    assert (
        client.get(f"/api/v1/files?folder_id={folder_id}", headers=auth).json()["meta"]["count"]
        == 1
    )
    assert client.get("/api/v1/files?unfiled_only=true", headers=auth).json()["meta"]["count"] == 1
    assert client.get("/api/v1/files?extension=.md", headers=auth).json()["meta"]["count"] == 1
    # A join, not a substring match: "work" must not find "homework".
    tagged = client.get("/api/v1/files?tag=work", headers=auth).json()
    assert [f["filename"] for f in tagged["data"]] == ["a.md"]


def test_tags_and_metadata_endpoints(client, auth, workspace_id) -> None:
    file_id = _create_file(client, auth, workspace_id, "a.txt").json()["data"]["id"]

    added = client.post(f"/api/v1/files/{file_id}/tags", json={"tag": "Invoice"}, headers=auth)
    assert added.status_code == 201
    assert added.json()["data"] == ["invoice"]
    assert client.get(f"/api/v1/files/{file_id}/tags", headers=auth).json()["data"] == ["invoice"]
    assert client.delete(f"/api/v1/files/{file_id}/tags/invoice", headers=auth).json()["data"] == []

    client.put(
        f"/api/v1/files/{file_id}/metadata", json={"key": "checksum", "value": "abc"}, headers=auth
    )
    assert client.get(f"/api/v1/files/{file_id}/metadata", headers=auth).json()["data"] == {
        "checksum": "abc"
    }
    assert (
        client.delete(f"/api/v1/files/{file_id}/metadata/checksum", headers=auth).status_code == 200
    )
    assert (
        client.delete(f"/api/v1/files/{file_id}/metadata/checksum", headers=auth).status_code == 404
    )


def test_index_endpoints_report_the_real_status(client, auth, workspace_id) -> None:
    indexed = _create_file(client, auth, workspace_id, "a.md", b"# hello").json()["data"]["id"]
    skipped = _create_file(client, auth, workspace_id, "b.png", b"\x89PNG").json()["data"]["id"]

    assert (
        client.get(f"/api/v1/files/{indexed}/index", headers=auth).json()["data"]["status"]
        == "indexed"
    )
    assert (
        client.get(f"/api/v1/files/{skipped}/index", headers=auth).json()["data"]["status"]
        == "skipped"
    )

    reindexed = client.post(f"/api/v1/files/{indexed}/index", headers=auth)
    assert reindexed.json()["meta"]["reindexed"] is True


def test_file_context_and_stats(client, auth, workspace_id) -> None:
    file_id = _create_file(client, auth, workspace_id, "a.md", b"# hello").json()["data"]["id"]

    context = client.get(f"/api/v1/files/{file_id}/context", headers=auth).json()["data"]
    assert context["file"]["filename"] == "a.md"
    assert context["index"]["status"] == "indexed"
    assert context["attached_to"] == []

    stats = client.get(f"/api/v1/files/stats?workspace_id={workspace_id}", headers=auth).json()[
        "data"
    ]
    assert stats["file_count"] == 1
    assert stats["total_bytes"] == 7


# --- Attachments ----------------------------------------------------------------


def test_attachment_round_trip(client, auth, workspace_id) -> None:
    file_id = _create_file(client, auth, workspace_id, "a.txt").json()["data"]["id"]
    note_id = client.post(
        "/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=auth
    ).json()["data"]["id"]

    attached = client.post(
        "/api/v1/attachments",
        json={"file_id": file_id, "target": "note", "target_id": note_id, "caption": "Agenda"},
        headers=auth,
    )
    assert attached.status_code == 201
    payload = attached.json()["data"]
    assert payload["target"] == "note"
    assert payload["target_id"] == note_id

    for_target = client.get(
        f"/api/v1/attachments/for-target?target=note&target_id={note_id}", headers=auth
    ).json()["data"]
    assert for_target["count"] == 1
    assert for_target["attachments"][0]["file"]["filename"] == "a.txt"

    for_file = client.get(f"/api/v1/attachments/for-file/{file_id}", headers=auth).json()["data"]
    assert for_file["count"] == 1

    detached = client.delete(f"/api/v1/attachments/{payload['id']}", headers=auth)
    assert detached.json()["data"]["file_deleted"] is False
    # Detaching is not deleting.
    assert client.get(f"/api/v1/files/{file_id}", headers=auth).status_code == 200


def test_attaching_to_an_unknown_target_kind_is_a_400(client, auth, workspace_id) -> None:
    file_id = _create_file(client, auth, workspace_id, "a.txt").json()["data"]["id"]

    response = client.post(
        "/api/v1/attachments",
        json={"file_id": file_id, "target": "spaceship", "target_id": "x"},
        headers=auth,
    )
    assert response.status_code == 400
    assert "Unknown attachment target" in response.json()["detail"]
