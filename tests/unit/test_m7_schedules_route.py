"""Schedules REST tests -- Milestone 7 Phase 6 (Scheduler MVP).

Against the real FastAPI app and the real DI container, matching
``test_m12_sensors_route.py``'s pattern. Permission is granted through
the existing generic plugin-permissions route, never ``PermissionModel``
directly.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jarvis.services.schedule_service import SCHEDULER_PRINCIPAL, SCHEDULER_SCOPE


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
        f"/api/v1/plugins/{SCHEDULER_PRINCIPAL}/permissions/{SCHEDULER_SCOPE}/grant",
        headers=auth,
    )
    assert response.status_code == 200


def _create_payload(**overrides) -> dict:
    payload = {
        "name": "Test schedule",
        "kind": "interval",
        "interval_seconds": 60.0,
        "steps": [{"kind": "automation", "instruction": "take a screenshot"}],
    }
    payload.update(overrides)
    return payload


# --- Auth ------------------------------------------------------------------------


def test_every_route_requires_a_session(client) -> None:
    for method, path in (
        ("get", "/api/v1/schedules"),
        ("get", "/api/v1/schedules/x"),
        ("post", "/api/v1/schedules"),
        ("post", "/api/v1/schedules/x/enable"),
        ("post", "/api/v1/schedules/x/disable"),
        ("delete", "/api/v1/schedules/x"),
        ("get", "/api/v1/schedules/x/executions"),
    ):
        assert getattr(client, method)(path).status_code in (401, 403)


# --- Permission gate ---------------------------------------------------------------


def test_create_denied_without_grant_is_400(client, auth) -> None:
    response = client.post("/api/v1/schedules", json=_create_payload(), headers=auth)
    assert response.status_code == 400
    assert "permission" in response.json()["detail"].lower()


def test_list_denied_without_grant_is_400(client, auth) -> None:
    response = client.get("/api/v1/schedules", headers=auth)
    assert response.status_code == 400


# --- Create / list / get -----------------------------------------------------------


def test_create_then_list_then_get(client, auth) -> None:
    _grant(client, auth)
    created = client.post("/api/v1/schedules", json=_create_payload(), headers=auth)
    assert created.status_code == 200
    schedule_id = created.json()["data"]["id"]

    listed = client.get("/api/v1/schedules", headers=auth)
    assert listed.status_code == 200
    assert listed.json()["meta"]["count"] == 1

    got = client.get(f"/api/v1/schedules/{schedule_id}", headers=auth)
    assert got.status_code == 200
    assert got.json()["data"]["id"] == schedule_id


def test_get_unknown_schedule_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/schedules/no-such-id", headers=auth)
    assert response.status_code == 404


def test_create_with_invalid_cron_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/schedules",
        json=_create_payload(kind="cron", cron_expression="not a cron", interval_seconds=0.0),
        headers=auth,
    )
    assert response.status_code == 400


def test_create_with_interval_below_minimum_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post(
        "/api/v1/schedules", json=_create_payload(interval_seconds=30.0), headers=auth
    )
    assert response.status_code == 400


def test_create_with_empty_steps_is_400(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/schedules", json=_create_payload(steps=[]), headers=auth)
    assert response.status_code == 400


# --- Enable / disable / delete ------------------------------------------------------


def test_disable_then_enable_round_trip(client, auth) -> None:
    _grant(client, auth)
    schedule_id = client.post("/api/v1/schedules", json=_create_payload(), headers=auth).json()[
        "data"
    ]["id"]

    disabled = client.post(f"/api/v1/schedules/{schedule_id}/disable", headers=auth)
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False

    enabled = client.post(f"/api/v1/schedules/{schedule_id}/enable", headers=auth)
    assert enabled.status_code == 200
    assert enabled.json()["data"]["enabled"] is True


def test_enable_unknown_schedule_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/schedules/no-such-id/enable", headers=auth)
    assert response.status_code == 404


def test_delete_then_get_is_404(client, auth) -> None:
    _grant(client, auth)
    schedule_id = client.post("/api/v1/schedules", json=_create_payload(), headers=auth).json()[
        "data"
    ]["id"]

    deleted = client.delete(f"/api/v1/schedules/{schedule_id}", headers=auth)
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True

    got = client.get(f"/api/v1/schedules/{schedule_id}", headers=auth)
    assert got.status_code == 404


# --- Executions ---------------------------------------------------------------------


def test_list_executions_for_unknown_schedule_is_404(client, auth) -> None:
    _grant(client, auth)
    response = client.get("/api/v1/schedules/no-such-id/executions", headers=auth)
    assert response.status_code == 404


def test_list_executions_for_a_never_fired_schedule_is_empty(client, auth) -> None:
    _grant(client, auth)
    schedule_id = client.post("/api/v1/schedules", json=_create_payload(), headers=auth).json()[
        "data"
    ]["id"]

    response = client.get(f"/api/v1/schedules/{schedule_id}/executions", headers=auth)
    assert response.status_code == 200
    assert response.json()["data"] == []


# --- Envelope shape -----------------------------------------------------------------


def test_response_envelope_matches_every_other_resource_router(client, auth) -> None:
    _grant(client, auth)
    response = client.post("/api/v1/schedules", json=_create_payload(), headers=auth)
    body = response.json()
    assert set(body.keys()) == {"data", "meta"}
