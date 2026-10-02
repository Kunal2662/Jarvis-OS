"""Workflow Builder REST tests -- M7 (standalone workflow authoring).

Against the real FastAPI app and the real DI container, matching
``test_m7_home_automation_route.py``'s pattern exactly. Permission is
granted through the existing generic plugin-permissions route, never
``PermissionModel`` directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

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


def _grant(client, auth) -> None:
    response = client.post(
        f"/api/v1/plugins/{WORKFLOW_BUILDER_PRINCIPAL}/permissions/{WORKFLOW_BUILDER_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Test workflow",
        "steps": [{"kind": "automation", "instruction": "take a screenshot"}],
    }
    payload.update(overrides)
    return payload


# --- Auth ------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/workflows"),
        ("get", "/api/v1/workflows/x"),
        ("post", "/api/v1/workflows"),
        ("patch", "/api/v1/workflows/x"),
        ("delete", "/api/v1/workflows/x"),
        ("post", "/api/v1/workflows/x/run"),
        ("get", "/api/v1/workflows/x/executions"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate ---------------------------------------------------------------


def test_create_denied_without_grant_is_400(client, auth) -> None:
    response = client.post("/api/v1/workflows", json=_create_payload(), headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/workflows", headers=auth)
    assert response.status_code == 400


# --- Create / list / get -----------------------------------------------------------


def test_create_then_list_then_get(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/workflows", json=_create_payload(), headers=auth)
    assert created.status_code == 200
    data = created.json()["data"]
    workflow_id = data["id"]
    assert data["name"] == "Test workflow"
    assert len(data["steps"]) == 1

    listed = client.get("/api/v1/workflows", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    got = client.get(f"/api/v1/workflows/{workflow_id}", headers=auth)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == workflow_id


def test_get_unknown_workflow_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/workflows/no-such-id", headers=auth)
    assert response.status_code == 404


def test_create_with_empty_name_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/workflows", json=_create_payload(name=""), headers=auth)
    assert response.status_code == 400


def test_create_with_empty_steps_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/workflows", json=_create_payload(steps=[]), headers=auth)
    assert response.status_code == 400


def test_create_with_invalid_step_kind_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/workflows",
        json=_create_payload(steps=[{"kind": "not_a_real_kind"}]),
        headers=auth,
    )
    assert response.status_code == 400


# --- Update ------------------------------------------------------------------------


def test_patch_name_only_leaves_steps_unchanged(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/workflows", json=_create_payload(), headers=auth).json()["data"]

    patched = client.patch(
        f"/api/v1/workflows/{created['id']}", json={"name": "Renamed"}, headers=auth
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "Renamed"
    assert patched.json()["data"]["steps"] == created["steps"]


def test_patch_steps_replaces_the_step_list(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/workflows", json=_create_payload(), headers=auth).json()["data"]

    new_steps = [{"kind": "agent_tool", "tool_name": "list_sensors"}]
    patched = client.patch(
        f"/api/v1/workflows/{created['id']}", json={"steps": new_steps}, headers=auth
    )
    assert patched.status_code == 200
    assert patched.json()["data"]["steps"][0]["kind"] == "agent_tool"
    assert patched.json()["data"]["steps"][0]["tool_name"] == "list_sensors"


def test_patch_with_invalid_steps_is_400(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/workflows", json=_create_payload(), headers=auth).json()["data"]

    patched = client.patch(
        f"/api/v1/workflows/{created['id']}",
        json={"steps": [{"kind": "not_a_real_kind"}]},
        headers=auth,
    )
    assert patched.status_code == 400


def test_patch_unknown_workflow_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.patch("/api/v1/workflows/no-such-id", json={"name": "y"}, headers=auth)
    assert response.status_code == 404


# --- Delete --------------------------------------------------------------------------


def test_delete_then_get_is_404(client, auth) -> None:
    _grant(client, auth)
    workflow_id = client.post("/api/v1/workflows", json=_create_payload(), headers=auth).json()[
        "data"
    ]["id"]

    deleted = client.delete(f"/api/v1/workflows/{workflow_id}", headers=auth)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True

    got = client.get(f"/api/v1/workflows/{workflow_id}", headers=auth)
    assert got.status_code == 404


def test_delete_unknown_workflow_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.delete("/api/v1/workflows/no-such-id", headers=auth)
    assert response.status_code == 404


# --- Manual run ----------------------------------------------------------------------


def test_run_unknown_workflow_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/workflows/no-such-id/run", headers=auth)
    assert response.status_code == 404


def test_run_executes_the_workflow_and_records_manual_source(client, auth) -> None:
    _grant(client, auth)
    # A read-only agent-tool step (list_sensors) -- deliberately not the
    # default OS-automation step, so this test never touches the real
    # desktop the unmocked AutomationService would otherwise attempt.
    # SensorService gates list_sensors behind its own, independent
    # permission scope -- grant it too.
    client.post("/api/v1/plugins/core:sensors/permissions/smart_home/grant", headers=auth)
    workflow_id = client.post(
        "/api/v1/workflows",
        json=_create_payload(steps=[{"kind": "agent_tool", "tool_name": "list_sensors"}]),
        headers=auth,
    ).json()["data"]["id"]

    response = client.post(f"/api/v1/workflows/{workflow_id}/run", headers=auth)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "manual"
    assert data["status"] == "succeeded"

    executions = client.get(f"/api/v1/workflows/{workflow_id}/executions", headers=auth)
    assert executions.status_code == 200
    assert executions.json()["meta"]["count"] == 1
    assert executions.json()["data"][0]["source"] == "manual"


# --- Executions ---------------------------------------------------------------------


def test_list_executions_for_unknown_workflow_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/workflows/no-such-id/executions", headers=auth)
    assert response.status_code == 404


def test_list_executions_empty_for_a_never_run_workflow(client, auth) -> None:
    _grant(client, auth)
    workflow_id = client.post("/api/v1/workflows", json=_create_payload(), headers=auth).json()[
        "data"
    ]["id"]

    response = client.get(f"/api/v1/workflows/{workflow_id}/executions", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"] == []
