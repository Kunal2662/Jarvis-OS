"""AI Workspace end-to-end -- Milestone 11 Task Group D.

Drives the real DI container, the real REST app, the real EventBus, the
real ``RuntimeWebSocketHub``, the real ``SearchService`` and the real
``KnowledgeService``. The unit tests prove each piece; this proves they
are wired to each other -- that ingestion through REST reaches the
shared knowledge graph, that a scoped retrieval narrows the *shared*
search index rather than a private one, that the agent's tool registry
grew the workspace tools, and that the two new events reach a real
WebSocket subscriber.

Only the LLM is faked, at the container's own ``llm_provider`` seam.
Everything downstream of it is the production object.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from tests.fakes.fake_llm import FakeLLM

_EXTRACTION = json.dumps(
    {
        "entities": [
            {"name": "Ada", "type": "person", "description": "a colleague"},
            {"name": "Migration", "type": "project", "description": "the cutover"},
        ],
        "relationships": [{"subject": "Ada", "predicate": "works_on", "object": "Migration"}],
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
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    container.runtime_ws_hub().stop()
    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}, session["session_id"]


def _workspace(client, headers, name: str = "Research") -> str:
    return client.post(
        "/api/v1/workspaces",
        json={"name": name, "description": "the migration"},
        headers=headers,
    ).json()["data"]["id"]


# --- wiring ---------------------------------------------------------------------


def test_ingestion_through_rest_reaches_the_shared_knowledge_graph(client, auth) -> None:
    """One graph, not a second one for workspaces: the entities the
    ingest route created are the ones ``/api/v1/knowledge`` returns."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)

    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)

    graph = asyncio.run(client.container.knowledge_service().search("Ada", top_k=10))
    linked = client.get(f"/api/v1/workspace-ai/{workspace_id}/entities", headers=headers).json()[
        "data"
    ]

    assert {hit.title for hit in graph} >= {"Ada"}
    assert {row["id"] for row in linked} == {hit.id for hit in graph if hit.title == "Ada"} | {
        row["id"] for row in linked if row["name"] != "Ada"
    }


def test_extraction_goes_through_knowledge_service_not_a_second_extractor(client, auth) -> None:
    """The relationship in the canned extraction lands in the graph,
    which only ``KnowledgeService.learn_from_text`` knows how to do."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)

    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)

    detail = asyncio.run(client.container.knowledge_service().get_entity_detail("Ada"))
    assert detail is not None
    assert [rel.predicate for rel in detail.relationships] == ["works_on"]


def test_scoped_retrieval_narrows_the_shared_search_service(client, auth) -> None:
    """Not a second index: the same ``SearchService`` every other source
    is registered against, filtered by workspace after ranking."""
    headers, _ = auth
    mine = _workspace(client, headers, "Quantum mine")
    theirs = _workspace(client, headers, "Quantum theirs")
    client.post(
        "/api/v1/notes", json={"workspace_id": mine, "title": "Quantum note"}, headers=headers
    )
    client.post(
        "/api/v1/notes", json={"workspace_id": theirs, "title": "Quantum note"}, headers=headers
    )

    shared = asyncio.run(client.container.search_service().search("quantum", top_k=30))
    scoped = client.get(
        f"/api/v1/workspace-ai/{mine}/retrieve?q=quantum&top_k=30", headers=headers
    ).json()["data"]

    assert len(shared) > len(scoped)  # the shared index sees both workspaces
    assert all(row["metadata"].get("workspace_id") in (mine, None) for row in scoped)
    assert all(row["id"] != theirs for row in scoped)


def test_task_group_d_registers_no_new_search_source(client) -> None:
    """A deliberate omission. Knowledge entities are already searchable
    through ``KnowledgeSearchSource``; a second source over the same rows
    would return the same entity twice with no way to tell the hits
    apart."""
    sources = {s.source_type for s in client.container.search_service().get_sources()}

    assert "workspace_links" not in sources
    assert "knowledge" in sources
    # Everything Task Groups A-C registered is still there.
    assert {"workspaces", "projects", "notes"} <= sources
    assert {"tasks", "calendar", "reminders"} <= sources
    assert {"files", "folders", "attachments"} <= sources


def test_the_agent_registry_grew_the_workspace_tools(client) -> None:
    """The workspace domain reaches the agent as tools on the *existing*
    registry, not as a second orchestrator."""
    from jarvis.agents.tools import build_tool_registry

    tools = build_tool_registry(workspace_assistant=client.container.workspace_assistant_service())

    assert {t.name for t in tools} == {
        "list_workspaces",
        "workspace_context",
        "search_workspace",
        "ask_workspace",
        "summarize_workspace",
    }


def test_a_workspace_tool_answers_from_real_wiring(client, auth) -> None:
    from jarvis.agents.tools import build_tool_registry

    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Cutover", "content": "Friday"},
        headers=headers,
    )
    tools = {
        t.name: t
        for t in build_tool_registry(
            workspace_assistant=client.container.workspace_assistant_service()
        )
    }

    rendered = asyncio.run(tools["workspace_context"].ainvoke({"workspace_id": workspace_id}))

    assert "Research" in rendered
    assert "Cutover" in rendered


def test_the_two_new_events_reach_a_real_websocket_subscriber(client, auth) -> None:
    """One EventBus, one relay -- not a second notification path bolted
    onto the AI layer."""
    headers, token = auth
    workspace_id = _workspace(client, headers)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()  # workspace.updated, from creating it above
        client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)
        client.post(f"/api/v1/workspace-ai/{workspace_id}/assist", json={}, headers=headers)

        # Three, not two: ingestion also drives the *shared*
        # KnowledgeService, whose own `knowledge.entity_updated` is
        # relayed on the same hub. That it arrives is the point -- one
        # graph, one bus, one relay.
        frames = [ws.receive_json() for _ in range(3)]

    types = [frame["type"] for frame in frames]
    assert types == [
        "knowledge.entity_updated",
        "workspace.knowledge_linked",
        "workspace.assisted",
    ]


def test_the_assist_event_carries_no_answer_text(client, auth) -> None:
    headers, token = auth
    workspace_id = _workspace(client, headers)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.receive_json()
        client.post(f"/api/v1/workspace-ai/{workspace_id}/assist", json={}, headers=headers)
        frame = ws.receive_json()

    assert frame["type"] == "workspace.assisted"
    assert set(frame["payload"]) >= {"workspace_id", "mode", "synthesized", "citation_count"}
    assert "answer" not in frame["payload"]


# --- the whole path -------------------------------------------------------------


def test_ingest_then_context_shows_evidence_rather_than_a_word_match(client, auth) -> None:
    """The point of the whole task group: after ingestion the knowledge
    section reports what this workspace's own text produced, not what
    happens to share a word with its name."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)

    before = client.get(f"/api/v1/workspace-ai/{workspace_id}/context", headers=headers).json()[
        "data"
    ]
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)
    after = client.get(f"/api/v1/workspace-ai/{workspace_id}/context", headers=headers).json()[
        "data"
    ]

    def _knowledge(payload):
        return next(s for s in payload["sections"] if s["name"] == "knowledge")

    assert _knowledge(before)["items"] == []
    assert {item["title"] for item in _knowledge(after)["items"]} == {"Ada", "Migration"}
    assert "link(s)" in _knowledge(after)["items"][0]["detail"]


def test_the_workspace_context_route_reports_the_same_links(client, auth) -> None:
    """Task Group A's ``/context`` gained ``linked_knowledge`` without
    losing anything it already returned -- the additive shape it
    promised."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)

    body = client.get(f"/api/v1/workspaces/{workspace_id}/context", headers=headers).json()["data"]

    assert set(body) >= {
        "workspace",
        "settings",
        "metadata",
        "projects",
        "notes",
        "related_knowledge",
        "related_memories",
        "linked_knowledge",
    }
    assert {row["name"] for row in body["linked_knowledge"]} == {"Ada", "Migration"}


def test_assist_grounds_its_prompt_in_the_real_assembled_context(client, auth) -> None:
    """Including a task with no due date, which is most of them -- the
    agenda's overdue/due-soon split would leave it out."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(
        "/api/v1/notes",
        json={"workspace_id": workspace_id, "title": "Cutover", "content": "Friday"},
        headers=headers,
    )
    client.post(
        "/api/v1/tasks",
        json={"workspace_id": workspace_id, "title": "Book the room"},
        headers=headers,
    )

    body = client.post(
        f"/api/v1/workspace-ai/{workspace_id}/assist", json={}, headers=headers
    ).json()

    prompt = client.container.llm_provider().calls[-1][0].content
    assert "Cutover" in prompt
    assert "Book the room" in prompt
    assert body["meta"]["synthesized"] is True


def test_a_link_survives_reingestion_when_a_person_asserted_it(client, auth) -> None:
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)
    entity_id = client.get(f"/api/v1/workspace-ai/{workspace_id}/entities", headers=headers).json()[
        "data"
    ][0]["id"]
    client.post(
        "/api/v1/knowledge-links",
        json={"workspace_id": workspace_id, "entity_id": entity_id, "source": "manual"},
        headers=headers,
    )

    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)

    manual = client.get(
        f"/api/v1/knowledge-links?workspace_id={workspace_id}&source=manual", headers=headers
    ).json()
    assert manual["meta"]["count"] == 1


def test_deleting_the_workspace_removes_its_links(client, auth) -> None:
    """Foreign keys are enforced and the ORM cascade is declared; a link
    to a deleted workspace must not survive either path."""
    headers, _ = auth
    workspace_id = _workspace(client, headers)
    client.post(f"/api/v1/workspace-ai/{workspace_id}/ingest", json={}, headers=headers)

    client.delete(f"/api/v1/workspaces/{workspace_id}", headers=headers)

    remaining = client.get(
        f"/api/v1/knowledge-links?workspace_id={workspace_id}", headers=headers
    ).json()
    assert remaining["meta"]["count"] == 0
