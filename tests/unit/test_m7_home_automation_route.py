"""Home Automation REST tests -- M7 (event-based triggers).

Against the real FastAPI app and the real DI container, matching
``test_m7_schedules_route.py``'s pattern exactly. Permission is
granted through the existing generic plugin-permissions route, never
``PermissionModel`` directly. ``device_id`` is a plain string field on
``AutomationTrigger`` (deliberately no FK to a real ``Device`` row --
matches ``DeviceStateChangedEvent.device_id``'s own unconstrained
shape), so these REST-layer tests never need to register a real
device.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.home_automation_service import HOME_AUTOMATION_PRINCIPAL, HOME_AUTOMATION_SCOPE


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
        f"/api/v1/plugins/{HOME_AUTOMATION_PRINCIPAL}/permissions/{HOME_AUTOMATION_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Test automation",
        "device_id": "light-123",
        "to_status": "paired",
        "steps": [{"kind": "automation", "instruction": "take a screenshot"}],
    }
    payload.update(overrides)
    return payload


# --- Auth ------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/home-automation"),
        ("get", "/api/v1/home-automation/x"),
        ("post", "/api/v1/home-automation"),
        ("post", "/api/v1/home-automation/x/enable"),
        ("post", "/api/v1/home-automation/x/disable"),
        ("delete", "/api/v1/home-automation/x"),
        ("post", "/api/v1/home-automation/x/run"),
        ("get", "/api/v1/home-automation/x/executions"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate ---------------------------------------------------------------


def test_create_denied_without_grant_is_400(client, auth) -> None:
    response = client.post("/api/v1/home-automation", json=_create_payload(), headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/home-automation", headers=auth)
    assert response.status_code == 400


# --- Create / list / get -----------------------------------------------------------


def test_create_then_list_then_get(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/home-automation", json=_create_payload(), headers=auth)
    assert created.status_code == 200
    data = created.json()["data"]
    trigger_id = data["id"]
    assert data["device_id"] == "light-123"
    assert data["to_status"] == "paired"
    assert data["from_status"] == ""
    assert data["enabled"] is True

    listed = client.get("/api/v1/home-automation", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    got = client.get(f"/api/v1/home-automation/{trigger_id}", headers=auth)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == trigger_id


def test_create_with_from_status(client, auth) -> None:
    _grant(client, auth)
    created = client.post(
        "/api/v1/home-automation",
        json=_create_payload(from_status="offline"),
        headers=auth,
    )
    assert created.status_code == 200
    assert created.json()["data"]["from_status"] == "offline"


def test_get_unknown_automation_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/home-automation/no-such-id", headers=auth)
    assert response.status_code == 404


def test_create_with_empty_device_id_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/home-automation", json=_create_payload(device_id=""), headers=auth
    )
    assert response.status_code == 400


def test_create_with_empty_to_status_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/home-automation", json=_create_payload(to_status=""), headers=auth
    )
    assert response.status_code == 400


def test_create_with_empty_steps_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/home-automation", json=_create_payload(steps=[]), headers=auth)
    assert response.status_code == 400


def test_create_with_invalid_step_kind_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/home-automation",
        json=_create_payload(steps=[{"kind": "not_a_real_kind"}]),
        headers=auth,
    )
    assert response.status_code == 400


# --- Enable / disable / delete ------------------------------------------------------


def test_disable_then_enable_round_trip(client, auth) -> None:
    _grant(client, auth)
    trigger_id = client.post(
        "/api/v1/home-automation", json=_create_payload(), headers=auth
    ).json()["data"]["id"]

    disabled = client.post(f"/api/v1/home-automation/{trigger_id}/disable", headers=auth)
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    enabled = client.post(f"/api/v1/home-automation/{trigger_id}/enable", headers=auth)
    assert enabled.status_code == 200
    assert enabled.json()["data"]["enabled"] is True


def test_enable_unknown_automation_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/home-automation/no-such-id/enable", headers=auth)
    assert response.status_code == 404


def test_delete_then_get_is_404(client, auth) -> None:
    _grant(client, auth)
    trigger_id = client.post(
        "/api/v1/home-automation", json=_create_payload(), headers=auth
    ).json()["data"]["id"]

    deleted = client.delete(f"/api/v1/home-automation/{trigger_id}", headers=auth)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True

    got = client.get(f"/api/v1/home-automation/{trigger_id}", headers=auth)
    assert got.status_code == 404


# --- Manual run ----------------------------------------------------------------------


def test_run_unknown_automation_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/home-automation/no-such-id/run", headers=auth)
    assert response.status_code == 404


def test_run_executes_the_workflow_and_records_manual_source(client, auth) -> None:
    _grant(client, auth)
    # A read-only agent-tool step (list_sensors) -- deliberately not the
    # default OS-automation step, so this test never touches the real
    # desktop (screenshot, etc.) the unmocked AutomationService would
    # otherwise attempt. SensorService gates list_sensors behind its
    # own, independent permission scope -- grant it too.
    client.post("/api/v1/plugins/core:sensors/permissions/smart_home/grant", headers=auth)
    trigger_id = client.post(
        "/api/v1/home-automation",
        json=_create_payload(steps=[{"kind": "agent_tool", "tool_name": "list_sensors"}]),
        headers=auth,
    ).json()["data"]["id"]

    response = client.post(f"/api/v1/home-automation/{trigger_id}/run", headers=auth)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["source"] == "manual"
    assert data["status"] == "succeeded"

    executions = client.get(f"/api/v1/home-automation/{trigger_id}/executions", headers=auth)
    assert executions.status_code == 200
    assert executions.json()["meta"]["count"] == 1
    assert executions.json()["data"][0]["source"] == "manual"


# --- Executions ---------------------------------------------------------------------


def test_list_executions_for_unknown_automation_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/home-automation/no-such-id/executions", headers=auth)
    assert response.status_code == 404


def test_list_executions_empty_for_a_never_fired_automation(client, auth) -> None:
    _grant(client, auth)
    trigger_id = client.post(
        "/api/v1/home-automation", json=_create_payload(), headers=auth
    ).json()["data"]["id"]

    response = client.get(f"/api/v1/home-automation/{trigger_id}/executions", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"] == []
