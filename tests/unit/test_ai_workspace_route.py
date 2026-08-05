"""AI Workspace REST tests -- Milestone 11 Task Group D.

Against the real FastAPI app and the real DI container, matching
``test_files_route.py``. The LLM provider is overridden with
``FakeLLM`` -- these tests assert the *route*, and a route that only
passes when a local model is running is not a test of the route.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM

#: A canned extraction the real ``KnowledgeService`` can parse, so the
#: ingest route exercises the genuine extract-then-link path rather than
#: the "nothing extracted" degradation.
_EXTRACTION = json.dumps(
    {
        "entities": [
            {"name": "Ada", "type": "person", "description": "a colleague"},
            {"name": "Migration", "type": "project", "description": "the cutover"},
        ],
        "relationships": [],
    }
)


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
    container.llm_provider.override(FakeLLM(_EXTRACTION))

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
    return client.post(
        "/api/v1/workspaces",
        json={"name": "Research", "description": "the migration"},
        headers=auth,
    ).json()["data"]["id"]


def _entity_id(client, auth, workspace_id: str) -> str:
    """Creates a real knowledge entity by ingesting, then reads its id
    back -- foreign keys are enforced, so a fabricated id is refused."""
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=auth)
    entities = client.get(f"/api/v1/workspace-ai/{workspace_id}/entities", headers=auth).json()[
        "data"
    ]
    return str(entities[0]["id"])


# --- Auth + envelope ------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/knowledge-links").status_code in (401, 403)
    assert client.get("/api/v1/workspace-ai/x/context").status_code in (401, 403)
    assert client.post("/api/v1/workspace-ai/x/assist", json={}).status_code in (401, 403)


def test_responses_use_the_documented_envelope(client, auth, workspace_id) -> None:
    body = client.get(f"/api/v1/workspace-ai/{workspace_id}/context", headers=auth).json()
    assert set(body) == {"data", "meta"}
    assert body["meta"]["budget_chars"] > 0


# --- context --------------------------------------------------------------------


def test_context_returns_the_packed_payload(client, auth, workspace_id) -> None:
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Standup", "content": "we discussed it"},
        headers=auth,
    )

    body = client.get(f"/api/v1/workspace-ai/{workspace_id}/context", headers=auth).json()

    assert body["data"]["workspace_name"] == "Research"
    assert "Standup" in body["data"]["text"]
    assert {section["name"] for section in body["data"]["sections"]} >= {"workspace", "notes"}


def test_context_honours_a_budget_query_parameter(client, auth, workspace_id) -> None:
    for index in range(20):
        client.post(
            "/api/v1/notes",
            json={"workspace_id": workspace_id, "title": f"N{index}", "content": "x" * 300},
            headers=auth,
        )

    body = client.get(
        f"/api/v1/workspace-ai/{workspace_id}/context?budget_chars=400", headers=auth
    ).json()

    assert body["meta"]["used_chars"] <= 400
    assert "notes" in body["data"]["truncated_sections"]


def test_context_for_an_unknown_workspace_is_404(client, auth) -> None:
    assert client.get("/api/v1/workspace-ai/nope/context", headers=auth).status_code == 404


# --- retrieve -------------------------------------------------------------------


def test_retrieve_narrows_to_the_workspace(client, auth, workspace_id) -> None:
    other = client.post("/api/v1/workspaces", json={"name": "Other"}, headers=auth).json()["data"][
        "id"
    ]
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Quantum here"},
        headers=auth,
    )
    client.post(
        "/api/v1/notes", json={"workspace_id": other, "title": "Quantum there"}, headers=auth
    )

    body = client.get(
        f"/api/v1/workspace-ai/{workspace_id}/retrieve?q=quantum", headers=auth
    ).json()

    titles = [row["title"] for row in body["data"]]
    assert "Quantum here" in titles
    assert "Quantum there" not in titles


def test_retrieve_reports_the_query_and_a_count(client, auth, workspace_id) -> None:
    body = client.get(
        f"/api/v1/workspace-ai/{workspace_id}/retrieve?q=nothing-matches", headers=auth
    ).json()

    assert body["meta"] == {"count": 0, "query": "nothing-matches"}


def test_retrieve_requires_a_query(client, auth, workspace_id) -> None:
    assert (
        client.get(f"/api/v1/workspace-ai/{workspace_id}/retrieve", headers=auth).status_code == 422
    )


def test_retrieve_for_an_unknown_workspace_is_404(client, auth) -> None:
    assert client.get("/api/v1/workspace-ai/nope/retrieve?q=x", headers=auth).status_code == 404


# --- assist ---------------------------------------------------------------------


def test_assist_summarizes_by_default(client, auth, workspace_id) -> None:
    body = client.post(f"/api/v1/workspace-ai/{workspace_id}/assist", json={}, headers=auth).json()

    assert body["data"]["mode"] == "summarize"
    assert body["data"]["answer"]
    assert body["meta"]["synthesized"] is True


def test_assist_in_ask_mode_returns_citations(client, auth, workspace_id) -> None:
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Cutover", "content": "Friday"},
        headers=auth,
    )

    body = client.post(
        f"/api/v1/workspace-ai/{workspace_id}/assist",
        json={"mode": "ask", "question": "cutover"},
        headers=auth,
    ).json()

    assert body["meta"]["citations"] >= 1
    assert body["data"]["question"] == "cutover"


def test_assist_returns_the_context_it_used(client, auth, workspace_id) -> None:
    body = client.post(f"/api/v1/workspace-ai/{workspace_id}/assist", json={}, headers=auth).json()

    assert body["data"]["context"]["workspace_id"] == workspace_id


def test_an_unknown_mode_is_a_400(client, auth, workspace_id) -> None:
    response = client.post(
        f"/api/v1/workspace-ai/{workspace_id}/assist",
        json={"mode": "interpretive-dance"},
        headers=auth,
    )

    assert response.status_code == 400
    assert "Unknown assist mode" in response.json()["detail"]


def test_ask_without_a_question_is_a_400(client, auth, workspace_id) -> None:
    response = client.post(
        f"/api/v1/workspace-ai/{workspace_id}/assist", json={"mode": "ask"}, headers=auth
    )

    assert response.status_code == 400


def test_assisting_an_unknown_workspace_is_a_400(client, auth) -> None:
    """A ``ServiceError`` from a bad path parameter, reported as a bad
    request rather than a 500 -- nothing broke."""
    response = client.post("/api/v1/workspace-ai/nope/assist", json={}, headers=auth)

    assert response.status_code == 400


# --- ingest + entities ----------------------------------------------------------


def test_ingest_extracts_and_links(client, auth, workspace_id) -> None:
    body = client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=auth).json()

    assert body["data"]["targets_processed"] >= 1
    assert body["data"]["links_created"] == 2
    assert body["meta"]["workspace_id"] == workspace_id


def test_entities_lists_what_the_workspace_is_about(client, auth, workspace_id) -> None:
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=auth)

    body = client.get(f"/api/v1/workspace-ai/{workspace_id}/entities", headers=auth).json()

    assert {row["name"] for row in body["data"]} == {"Ada", "Migration"}
    assert body["meta"]["count"] == 2


def test_ingesting_an_unknown_workspace_is_a_400(client, auth) -> None:
    assert client.post("/api/v1/workspace-ai/nope/ingest", json={}, headers=auth).status_code == 400


def test_reingesting_does_not_multiply_links(client, auth, workspace_id) -> None:
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=auth)
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=auth)

    links = client.get(f"/api/v1/knowledge-links?workspace_id={workspace_id}", headers=auth).json()

    assert links["meta"]["count"] == 2


# --- knowledge links ------------------------------------------------------------


def test_a_link_can_be_created_listed_read_and_deleted(client, auth, workspace_id) -> None:
    entity_id = _entity_id(client, auth, workspace_id)
    note_id = client.post(
        "/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=auth
    ).json()["data"]["id"]

    created = client.post(
        "/api/v1/knowledge-links",
        json={
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "target": "note",
            "target_id": note_id,
        },
        headers=auth,
    )
    link_id = created.json()["data"]["id"]

    assert created.status_code == 201
    assert created.json()["data"]["target"] == "note"
    assert created.json()["data"]["source"] == "manual"
    assert client.get(f"/api/v1/knowledge-links/{link_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/v1/knowledge-links/{link_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/knowledge-links/{link_id}", headers=auth).status_code == 404


def test_links_can_be_filtered_by_target_and_source(client, auth, workspace_id) -> None:
    entity_id = _entity_id(client, auth, workspace_id)
    note_id = client.post(
        "/api/v1/notes", json={"workspace_id": workspace_id, "title": "N"}, headers=auth
    ).json()["data"]["id"]
    client.post(
        "/api/v1/knowledge-links",
        json={
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "target": "note",
            "target_id": note_id,
        },
        headers=auth,
    )

    by_target = client.get(
        f"/api/v1/knowledge-links?target=note&target_id={note_id}", headers=auth
    ).json()
    by_source = client.get("/api/v1/knowledge-links?source=manual", headers=auth).json()

    assert by_target["meta"]["count"] == 1
    assert by_source["meta"]["count"] == 1


def test_linking_a_fabricated_entity_is_a_400(client, auth, workspace_id) -> None:
    response = client.post(
        "/api/v1/knowledge-links",
        json={"workspace_id": workspace_id, "entity_id": "nope"},
        headers=auth,
    )

    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_an_unknown_target_kind_is_a_400(client, auth, workspace_id) -> None:
    entity_id = _entity_id(client, auth, workspace_id)

    response = client.post(
        "/api/v1/knowledge-links",
        json={
            "workspace_id": workspace_id,
            "entity_id": entity_id,
            "target": "event",
            "target_id": "x",
        },
        headers=auth,
    )

    assert response.status_code == 400


def test_an_unknown_filter_is_a_400(client, auth) -> None:
    assert client.get("/api/v1/knowledge-links?source=hunch", headers=auth).status_code == 400


def test_deleting_an_unknown_link_is_a_404(client, auth) -> None:
    assert client.delete("/api/v1/knowledge-links/nope", headers=auth).status_code == 404


def test_relinking_the_same_pair_returns_the_same_row(client, auth, workspace_id) -> None:
    entity_id = _entity_id(client, auth, workspace_id)
    body = {"workspace_id": workspace_id, "entity_id": entity_id}

    first = client.post("/api/v1/knowledge-links", json=body, headers=auth).json()
    second = client.post("/api/v1/knowledge-links", json=body, headers=auth).json()

    assert first["data"]["id"] == second["data"]["id"]


def test_a_manual_assertion_promotes_an_extracted_link(client, auth, workspace_id) -> None:
    """Asserting what the extractor already found upgrades it, so a
    later re-ingestion cannot remove it."""
    entity_id = _entity_id(client, auth, workspace_id)

    promoted = client.post(
        "/api/v1/knowledge-links",
        json={"workspace_id": workspace_id, "entity_id": entity_id, "source": "manual"},
        headers=auth,
    ).json()

    assert promoted["data"]["source"] == "manual"
