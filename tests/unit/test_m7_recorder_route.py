"""Recorder REST tests -- M7 Recorder.

Against the real FastAPI app and the real DI container, matching
``test_m7_workflow_builder_route.py``'s pattern exactly. Permission is
granted through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.recorder_service import RECORDER_PRINCIPAL, RECORDER_SCOPE
from jarvis.services.workflow_builder_service import (
    WORKFLOW_BUILDER_PRINCIPAL,
    WORKFLOW_BUILDER_SCOPE,
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


def _grant_recorder(client, auth) -> None:
    response = client.post(
        f"/api/v1/plugins/{RECORDER_PRINCIPAL}/permissions/{RECORDER_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _grant_workflow_builder(client, auth) -> None:
    response = client.post(
        f"/api/v1/plugins/{WORKFLOW_BUILDER_PRINCIPAL}/permissions/{WORKFLOW_BUILDER_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


# --- Auth ------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("post", "/api/v1/recordings/start"),
        ("post", "/api/v1/recordings/x/stop"),
        ("post", "/api/v1/recordings/x/cancel"),
        ("get", "/api/v1/recordings"),
        ("get", "/api/v1/recordings/x"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate ---------------------------------------------------------------


def test_start_denied_without_grant_is_400(client, auth) -> None:
    response = client.post("/api/v1/recordings/start", headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/recordings", headers=auth)
    assert response.status_code == 400


# --- Start / list / get -------------------------------------------------------------


def test_start_then_list_then_get(client, auth) -> None:
    _grant_recorder(client, auth)
    started = client.post("/api/v1/recordings/start", headers=auth)
    assert started.status_code == 200
    data = started.json()["data"]
    session_id = data["id"]
    assert data["status"] == "recording"

    listed = client.get("/api/v1/recordings", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    got = client.get(f"/api/v1/recordings/{session_id}", headers=auth)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == session_id


def test_get_unknown_session_is_404(client, auth) -> None:
    _grant_recorder(client, auth)
    response = client.get("/api/v1/recordings/no-such-id", headers=auth)
    assert response.status_code == 404


def test_start_while_active_is_400(client, auth) -> None:
    _grant_recorder(client, auth)
    client.post("/api/v1/recordings/start", headers=auth)
    second = client.post("/api/v1/recordings/start", headers=auth)
    assert second.status_code == 400
    assert "already active" in second.json()["detail"].lower()


# --- Cancel --------------------------------------------------------------------------


def test_cancel_then_get_shows_cancelled(client, auth) -> None:
    _grant_recorder(client, auth)
    session_id = client.post("/api/v1/recordings/start", headers=auth).json()["data"]["id"]

    cancelled = client.post(f"/api/v1/recordings/{session_id}/cancel", headers=auth)
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "cancelled"

    got = client.get(f"/api/v1/recordings/{session_id}", headers=auth)
    assert got.json()["data"]["status"] == "cancelled"


def test_cancel_unknown_session_is_404(client, auth) -> None:
    _grant_recorder(client, auth)
    response = client.post("/api/v1/recordings/no-such-id/cancel", headers=auth)
    assert response.status_code == 404


def test_cancelling_frees_the_active_slot(client, auth) -> None:
    _grant_recorder(client, auth)
    first = client.post("/api/v1/recordings/start", headers=auth).json()["data"]["id"]
    client.post(f"/api/v1/recordings/{first}/cancel", headers=auth)

    second = client.post("/api/v1/recordings/start", headers=auth)
    assert second.status_code == 200


# --- Stop --------------------------------------------------------------------------


def test_stop_unknown_session_is_404(client, auth) -> None:
    _grant_recorder(client, auth)
    response = client.post("/api/v1/recordings/no-such-id/stop", json={"name": "x"}, headers=auth)
    assert response.status_code == 404


def test_stop_with_nothing_captured_is_400(client, auth) -> None:
    _grant_recorder(client, auth)
    _grant_workflow_builder(client, auth)
    session_id = client.post("/api/v1/recordings/start", headers=auth).json()["data"]["id"]

    response = client.post(
        f"/api/v1/recordings/{session_id}/stop", json={"name": "x"}, headers=auth
    )
    assert response.status_code == 400


def test_stop_without_workflow_builder_permission_is_400(client, auth) -> None:
    """Recording permission alone must not be enough to create the
    resulting workflow (Logic Contract §11)."""
    _grant_recorder(client, auth)  # workflow_builder deliberately NOT granted
    session_id = client.post("/api/v1/recordings/start", headers=auth).json()["data"]["id"]

    # A real captured step so the failure is genuinely about permission,
    # not "nothing captured".
    automation_container = client.container  # type: ignore[attr-defined]
    workflow_executor = automation_container.workflow_execution_service()
    asyncio.run(
        workflow_executor.run_workflow([{"kind": "automation", "instruction": "take a screenshot"}])
    )

    response = client.post(
        f"/api/v1/recordings/{session_id}/stop", json={"name": "x"}, headers=auth
    )
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_stop_creates_and_returns_the_workflow(client, auth) -> None:
    _grant_recorder(client, auth)
    _grant_workflow_builder(client, auth)
    session_id = client.post("/api/v1/recordings/start", headers=auth).json()["data"]["id"]

    container = client.container  # type: ignore[attr-defined]
    workflow_executor = container.workflow_execution_service()
    asyncio.run(
        workflow_executor.run_workflow([{"kind": "automation", "instruction": "take a screenshot"}])
    )

    response = client.post(
        f"/api/v1/recordings/{session_id}/stop",
        json={"name": "Recorded Macro", "description": "desc"},
        headers=auth,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["resulting_workflow"]["name"] == "Recorded Macro"
    assert len(data["resulting_workflow"]["steps"]) == 1

    # Genuinely visible through Workflow Builder's own REST surface.
    listed = client.get("/api/v1/workflows", headers=auth)
    assert listed.json()["meta"]["count"] == 1
    assert listed.json()["data"][0]["id"] == data["resulting_workflow"]["id"]
