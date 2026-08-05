"""Pagination convention tests -- Milestone 11 Task Group F.

The pure helper, then the convention applied across every M11
collection route. The route tests are the ones that matter: the defect
this closes was not "no limit parameter", it was that a repository cap
truncated silently and ``meta.count`` looked like a complete answer.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.infrastructure.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Page,
    page_meta,
)

# --- the helper -----------------------------------------------------------------


def test_probe_limit_asks_for_one_more_than_wanted() -> None:
    """One extra row answers has_more exactly, and costs less than a
    COUNT(*) beside every listing."""
    assert Page(limit=25).probe_limit == 26


def test_trim_drops_the_probe_row_and_reports_more() -> None:
    rows, has_more = Page(limit=3).trim([1, 2, 3, 4])

    assert rows == [1, 2, 3]
    assert has_more is True


def test_trim_on_a_short_page_reports_no_more() -> None:
    rows, has_more = Page(limit=3).trim([1, 2])

    assert rows == [1, 2]
    assert has_more is False


def test_an_exactly_full_page_without_a_probe_row_is_the_last_one() -> None:
    rows, has_more = Page(limit=3).trim([1, 2, 3])

    assert rows == [1, 2, 3]
    assert has_more is False


def test_meta_keeps_count_meaning_what_it_always_did() -> None:
    """Additive: no existing caller reading `count` breaks."""
    meta = page_meta(page=Page(limit=10, offset=20), count=7, has_more=False)

    assert meta == {"count": 7, "limit": 10, "offset": 20, "has_more": False}


def test_meta_accepts_route_specific_extras() -> None:
    meta = page_meta(page=Page(), count=0, has_more=False, query="invoice")

    assert meta["query"] == "invoice"


def test_the_default_page_is_smaller_than_the_repository_caps() -> None:
    """A default that returns everything trains callers to assume a
    listing is complete -- the assumption this module exists to break."""
    assert DEFAULT_LIMIT < MAX_LIMIT
    # The number `docs/ARCHITECTURE.md` §5 specifies.
    assert MAX_LIMIT == 200


# --- the convention, across every M11 collection --------------------------------


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
        yield test_client
    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


@pytest.fixture
def workspace_id(client, auth) -> str:
    return client.post("/api/v1/workspaces", json={"name": "W"}, headers=auth).json()["data"]["id"]


def _seed_notes(client, auth, workspace_id: str, count: int) -> None:
    for index in range(count):
        client.post(
            "/api/v1/notes",
            json={"workspace_id": workspace_id, "title": f"N{index:02d}"},
            headers=auth,
        )


def test_a_page_reports_limit_offset_and_has_more(client, auth, workspace_id) -> None:
    _seed_notes(client, auth, workspace_id, 7)

    body = client.get("/api/v1/notes?limit=3", headers=auth).json()

    assert body["meta"] == {"count": 3, "limit": 3, "offset": 0, "has_more": True}


def test_the_last_page_says_there_is_no_more(client, auth, workspace_id) -> None:
    _seed_notes(client, auth, workspace_id, 7)

    body = client.get("/api/v1/notes?limit=3&offset=6", headers=auth).json()

    assert body["meta"]["count"] == 1
    assert body["meta"]["has_more"] is False


def test_pages_do_not_overlap_and_cover_everything(client, auth, workspace_id) -> None:
    _seed_notes(client, auth, workspace_id, 7)

    seen: list[str] = []
    offset = 0
    while True:
        body = client.get(f"/api/v1/notes?limit=2&offset={offset}", headers=auth).json()
        seen += [row["title"] for row in body["data"]]
        if not body["meta"]["has_more"]:
            break
        offset += 2

    assert len(seen) == len(set(seen)) == 7


def test_a_limit_above_the_maximum_is_refused_rather_than_clamped(client, auth) -> None:
    """422 naming the bound is more useful than quietly returning 500 and
    letting the caller believe it was everything."""
    assert client.get(f"/api/v1/notes?limit={MAX_LIMIT + 1}", headers=auth).status_code == 422


def test_a_zero_or_negative_limit_is_refused(client, auth) -> None:
    assert client.get("/api/v1/notes?limit=0", headers=auth).status_code == 422
    assert client.get("/api/v1/notes?offset=-1", headers=auth).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/workspaces",
        "/api/v1/projects",
        "/api/v1/notes",
        "/api/v1/tasks",
        "/api/v1/reminders",
        "/api/v1/files",
        "/api/v1/folders",
        "/api/v1/attachments",
        "/api/v1/knowledge-links",
    ],
)
def test_every_m11_collection_uses_the_same_meta_shape(client, auth, path) -> None:
    """One convention, not a limit parameter invented per router."""
    body = client.get(path, headers=auth).json()

    assert set(body["meta"]) >= {"count", "limit", "offset", "has_more"}
    assert body["meta"]["limit"] == DEFAULT_LIMIT
    assert body["meta"]["offset"] == 0


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/workspaces",
        "/api/v1/projects",
        "/api/v1/notes",
        "/api/v1/tasks",
        "/api/v1/reminders",
        "/api/v1/files",
        "/api/v1/folders",
        "/api/v1/attachments",
        "/api/v1/knowledge-links",
    ],
)
def test_every_m11_collection_bounds_its_limit(client, auth, path) -> None:
    assert client.get(f"{path}?limit=9999", headers=auth).status_code == 422


def test_paging_is_stable_across_a_filtered_collection(client, auth, workspace_id) -> None:
    """Filters and paging compose: the filter narrows, the page slices
    what the filter left."""
    other = client.post("/api/v1/workspaces", json={"name": "Other"}, headers=auth).json()["data"]
    _seed_notes(client, auth, workspace_id, 4)
    _seed_notes(client, auth, other["id"], 4)

    body = client.get(f"/api/v1/notes?workspace_id={workspace_id}&limit=3", headers=auth).json()

    assert body["meta"]["count"] == 3
    assert body["meta"]["has_more"] is True
    second = client.get(
        f"/api/v1/notes?workspace_id={workspace_id}&limit=3&offset=3", headers=auth
    ).json()
    assert second["meta"]["count"] == 1
    assert second["meta"]["has_more"] is False
