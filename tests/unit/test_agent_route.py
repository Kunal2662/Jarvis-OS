"""Integration tests for the AI Orchestrator API's real FastAPI wiring --
``/api/v1/agent/*`` (Milestone 10). Real, in-process ``TestClient`` against
a real temp-file SQLite database, matching ``test_devtools_route.py`` /
``test_plugins_route.py``'s established pattern. The real ``ILLMProvider``
singleton is overridden with :class:`ScriptedFakeLLM` so these tests never
need a network call or an API key."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app
    from tests.fakes.fake_scripted_llm import ScriptedFakeLLM

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)
    container.llm_provider.override(
        ScriptedFakeLLM(
            {
                "tool-selection module": ('{"action": "final", "final_text": "The answer is 4."}'),
            }
        )
    )

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    with TestClient(app) as test_client:
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_agent_invoke_requires_auth(client) -> None:
    response = client.post("/api/v1/agent/invoke", json={"prompt": "hi"})
    assert response.status_code == 401


def test_agent_invoke_returns_envelope(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/agent/invoke", json={"prompt": "what is 2 + 2?"}, headers=auth_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["text"] == "The answer is 4."
    assert body["data"]["thread_id"]
    assert "steps" in body["data"]
    assert "metadata" in body["data"]


def test_agent_stream_requires_auth(client) -> None:
    response = client.post("/api/v1/agent/stream", json={"prompt": "hi"})
    assert response.status_code == 401


def test_agent_stream_returns_sse_frames(client, auth_headers) -> None:
    with client.stream(
        "POST", "/api/v1/agent/stream", json={"prompt": "hi"}, headers=auth_headers
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "data: " in body
    assert "event: done" in body
