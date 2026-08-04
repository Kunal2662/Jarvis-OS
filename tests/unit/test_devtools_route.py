"""Integration tests for the Developer Platform Tools API's actual
FastAPI wiring -- ``/api/v1/devtools/*`` (Milestone 9 Task Group E).
Real, in-process ``TestClient`` against a real temp-file SQLite
database, matching ``test_runtime_ws_route.py``'s established
pattern."""

from __future__ import annotations

import asyncio
import json
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
        test_client.tmp_path = tmp_path  # type: ignore[attr-defined]
        test_client.container = container  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_devtools_logs_requires_auth(client) -> None:
    assert client.get("/api/v1/devtools/logs").status_code == 401


def test_get_logs_captures_a_real_line(client, auth_headers) -> None:
    from loguru import logger as loguru_logger

    console = client.container.debug_console()
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.route").info("captured via the route")
        import time

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(console) == 0:
            time.sleep(0.02)
    finally:
        console.stop()

    response = client.get("/api/v1/devtools/logs", headers=auth_headers)
    assert response.status_code == 200
    messages = [e["message"] for e in response.json()["data"]]
    assert "captured via the route" in messages


def test_get_logs_filters_by_contains(client, auth_headers) -> None:
    from loguru import logger as loguru_logger

    console = client.container.debug_console()
    console.start(level="DEBUG")
    try:
        loguru_logger.bind(logger="jarvis.test.route").info("alpha-line")
        loguru_logger.bind(logger="jarvis.test.route").info("beta-line")
        import time

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and len(console) < 2:
            time.sleep(0.02)
    finally:
        console.stop()

    response = client.get(
        "/api/v1/devtools/logs", params={"contains": "alpha"}, headers=auth_headers
    )
    messages = [e["message"] for e in response.json()["data"]]
    assert "alpha-line" in messages
    assert "beta-line" not in messages


def test_clear_logs(client, auth_headers) -> None:
    response = client.delete("/api/v1/devtools/logs", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["cleared"] is True


def test_performance_current_and_metrics(client, auth_headers) -> None:
    current = client.get("/api/v1/devtools/performance", headers=auth_headers)
    assert current.status_code == 200
    assert current.json()["data"] == {}

    metrics = client.get("/api/v1/devtools/performance/metrics", headers=auth_headers)
    assert metrics.status_code == 200
    assert "cpu_percent" in metrics.json()["data"]


@pytest.mark.asyncio
async def test_performance_history_reflects_real_health_events(client, auth_headers) -> None:
    from jarvis.core.events.events import HealthUpdatedEvent

    profiler = client.container.performance_profiler()
    profiler.start()
    try:
        await client.container.event_bus().publish(
            HealthUpdatedEvent(snapshot={"cpu_percent": 42.0})
        )
    finally:
        profiler.stop()

    response = client.get("/api/v1/devtools/performance/cpu_percent/history", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"][0]["value"] == 42.0


def test_state_snapshot_shape(client, auth_headers) -> None:
    response = client.get("/api/v1/devtools/state", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert "services" in body
    assert "plugins" in body
    assert "startup_hooks" in body
    assert "shutdown_hooks" in body


def test_api_calls_records_prior_requests(client, auth_headers) -> None:
    client.get("/api/v1/devtools/state", headers=auth_headers)
    response = client.get("/api/v1/devtools/api-calls", headers=auth_headers)
    assert response.status_code == 200
    paths = [r["path"] for r in response.json()["data"]]
    assert "/api/v1/devtools/state" in paths


def test_api_calls_filters_by_path_contains(client, auth_headers) -> None:
    client.get("/api/v1/devtools/state", headers=auth_headers)
    client.get("/api/v1/devtools/performance", headers=auth_headers)
    response = client.get(
        "/api/v1/devtools/api-calls", params={"path_contains": "performance"}, headers=auth_headers
    )
    paths = [r["path"] for r in response.json()["data"]]
    assert all("performance" in p for p in paths)
    assert len(paths) >= 1


def _write_plugin(root: Path, plugin_id: str) -> Path:
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_id,
        "display_name": plugin_id.title(),
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "class HelloPlugin:\n"
        "    async def on_load(self, context) -> None: pass\n"
        "    async def on_start(self) -> None: pass\n"
        "    async def on_stop(self) -> None: pass\n",
        encoding="utf-8",
    )
    return plugin_dir


def test_plugin_diagnostics_combines_status_health_and_logs(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world")
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    response = client.get("/api/v1/devtools/plugins/hello-world/diagnostics", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["plugin_id"] == "hello-world"
    assert body["state"] == "running"
    assert body["healthy"] is True
    assert "recent_logs" in body
    assert "permission_audit" in body


def test_plugin_diagnostics_unknown_plugin_reports_unknown_state(client, auth_headers) -> None:
    response = client.get("/api/v1/devtools/plugins/ghost/diagnostics", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["state"] == "unknown"
