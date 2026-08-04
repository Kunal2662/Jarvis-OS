"""Integration tests for the Runtime WebSocket API's actual FastAPI
wiring -- ``/api/v1/sessions`` and ``/api/v1/ws`` (Milestone 9 Task
Group B). Uses a real, in-process ``TestClient`` against a real
(temp-file) SQLite database -- no mocked network, per this project's
own API testing standard (``docs/ARCHITECTURE.md`` §18)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings()
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

    import asyncio

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        yield test_client

    asyncio.run(database.dispose())


def test_create_session_returns_201_with_session_id(client) -> None:
    response = client.post("/api/v1/sessions", json={"metadata": {"client": "test"}})
    assert response.status_code == 201
    body = response.json()
    assert body["data"]["session_id"]
    assert body["data"]["conversation_id"] is None


def test_session_routes_use_the_documented_envelope(client) -> None:
    """``docs/ARCHITECTURE.md`` §5 mandates ``{data, meta}`` for every
    successful response. These routes were the last holdout; §15
    deferred the change until a second resource route existed to prove
    the shape, and six of them now do (Aug 2026 backlog pass)."""
    created = client.post("/api/v1/sessions", json={})
    fetched = client.get(f"/api/v1/sessions/{created.json()['data']['session_id']}")

    for response in (created, fetched):
        assert set(response.json()) == {"data", "meta"}
        assert isinstance(response.json()["meta"], dict)
    assert created.json()["meta"]["created"] is True


def test_get_unknown_session_returns_404(client) -> None:
    response = client.get("/api/v1/sessions/does-not-exist")
    assert response.status_code == 404


def test_get_session_round_trips(client) -> None:
    created = client.post("/api/v1/sessions", json={}).json()["data"]
    response = client.get(f"/api/v1/sessions/{created['session_id']}")
    assert response.status_code == 200
    assert response.json()["data"]["session_id"] == created["session_id"]


def test_close_session_then_get_returns_404(client) -> None:
    created = client.post("/api/v1/sessions", json={}).json()["data"]
    close = client.delete(f"/api/v1/sessions/{created['session_id']}")
    assert close.status_code == 204
    assert client.get(f"/api/v1/sessions/{created['session_id']}").status_code == 404


def test_ws_connect_without_token_is_rejected(client) -> None:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/v1/ws"):
        pass


def test_ws_connect_with_valid_session_receives_relayed_event(client) -> None:
    import asyncio

    from jarvis.core.di.container import Container
    from jarvis.core.events.events import ServiceStartedEvent

    session = client.post("/api/v1/sessions", json={}).json()["data"]

    with client.websocket_connect(f"/api/v1/ws?token={session['session_id']}") as ws:
        container: Container = client.app.state.container
        asyncio.run(container.event_bus().publish(ServiceStartedEvent(service="chat")))
        message = ws.receive_json()
        assert message["type"] == "service.started"
        assert message["payload"] == {"service": "chat"}


def test_ws_resume_replays_missed_events(client) -> None:
    import asyncio

    from jarvis.core.di.container import Container
    from jarvis.core.events.events import ServiceFailedEvent, ServiceStartedEvent

    session = client.post("/api/v1/sessions", json={}).json()["data"]
    container: Container = client.app.state.container
    token = session["session_id"]

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        asyncio.run(container.event_bus().publish(ServiceStartedEvent(service="chat")))
        last_id = ws.receive_json()["id"]

    # Missed while disconnected.
    asyncio.run(container.event_bus().publish(ServiceFailedEvent(service="chat", detail="oops")))

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.send_json({"type": "resume", "last_id": last_id})
        message = ws.receive_json()
        assert message["type"] == "service.failed"
        assert message["payload"]["detail"] == "oops"


def test_ws_resume_outside_window_reports_resume_failed(client) -> None:
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    token = session["session_id"]

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        ws.send_json({"type": "resume", "last_id": "never-seen"})
        message = ws.receive_json()
        assert message["type"] == "resume_failed"
