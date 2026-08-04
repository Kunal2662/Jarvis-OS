"""End-to-end Developer Platform Tools test (Milestone 9 Task Group E)
-- proves the new REST API (``routes/plugins.py``) genuinely drives the
real Task Group D ``PluginRegistry``/``PermissionModel`` *and* that the
result is genuinely relayed over the real Runtime WebSocket API
(Task Group B/C's ``RuntimeWebSocketHub``) -- the REST write side and
the WebSocket read side are exercised together, not each in isolation
against a double of the other.
"""

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
    container.runtime_ws_hub().start()

    with TestClient(app) as test_client:
        test_client.tmp_path = tmp_path  # type: ignore[attr-defined]
        yield test_client

    asyncio.run(database.dispose())


def _write_plugin(root: Path, plugin_id: str, *, permissions=()) -> Path:
    """The plugin's own ``on_load`` genuinely exercises the
    ``filesystem`` permission-gated surface (writing one real file
    under its own confined data dir) -- declaring a scope in the
    manifest alone never blocks loading (correctly so: least-privilege
    gates the *use* of a capability, not the mere declaration of
    intent to use it); only an actual gated call, made while the scope
    is still ``PENDING``, produces the real ``PluginPermissionError``
    this test exercises. ``filesystem`` (not ``hotkey``) is used
    deliberately -- no OS/display-server dependency, so this stays
    deterministic in a headless CI environment."""
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": plugin_id,
        "display_name": plugin_id.title(),
        "version": "1.0.0",
        "entry_point": "plugin:HelloPlugin",
        "permissions": list(permissions),
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text(
        "class HelloPlugin:\n"
        "    async def on_load(self, context) -> None:\n"
        "        context.filesystem.write_text('marker.txt', 'hello')\n"
        "    async def on_start(self) -> None: pass\n"
        "    async def on_stop(self) -> None: pass\n",
        encoding="utf-8",
    )
    return plugin_dir


def test_install_and_grant_via_rest_relay_over_websocket(client) -> None:
    session = client.post("/api/v1/sessions", json={}).json()
    token = session["session_id"]
    headers = {"Authorization": f"Bearer {token}"}

    source = _write_plugin(client.tmp_path / "staged", "hello-world", permissions=["filesystem"])

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        # ---- Act 1: install over REST -- PluginRegistry.install()
        # publishes PluginInstalledEvent directly (it does not go
        # through discover_and_load_all()'s own PluginDiscoveredEvent
        # step), then attempts a real load; since "filesystem" starts
        # PENDING, on_load's real filesystem.write_text() call genuinely
        # fails.
        install = client.post(
            "/api/v1/plugins/install", json={"source_path": str(source)}, headers=headers
        )
        assert install.status_code == 201

        seen_types = []
        for _ in range(2):
            message = ws.receive_json()
            seen_types.append(message["type"])
        assert seen_types == ["plugin.installed", "plugin.load_failed"]

        # ---- Act 2: grant the permission over REST -- expect
        # plugin.permission_granted, then a genuinely successful
        # plugin.loaded once re-enabled.
        grant = client.post(
            "/api/v1/plugins/hello-world/permissions/filesystem/grant", headers=headers
        )
        assert grant.status_code == 200
        granted_message = ws.receive_json()
        assert granted_message["type"] == "plugin.permission_granted"
        assert granted_message["payload"]["scope"] == "filesystem"

        enable = client.post("/api/v1/plugins/hello-world/enable", headers=headers)
        assert enable.status_code == 200
        assert enable.json()["data"]["enabled"] is True

        loaded_message = ws.receive_json()
        assert loaded_message["type"] == "plugin.loaded"
        assert loaded_message["payload"]["plugin_id"] == "hello-world"
        enabled_message = ws.receive_json()
        assert enabled_message["type"] == "plugin.enabled"

    # ---- Act 3: diagnostics over REST reflect the real, final state.
    diagnostics = client.get(
        "/api/v1/devtools/plugins/hello-world/diagnostics", headers=headers
    ).json()["data"]
    assert diagnostics["state"] == "running"
    assert diagnostics["healthy"] is True
    audit_actions = [e["action"] for e in diagnostics["permission_audit"]]
    assert "granted" in audit_actions
