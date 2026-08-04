"""Integration tests for the Plugin Marketplace Foundation + Permission
Management API's actual FastAPI wiring -- ``/api/v1/plugins``,
``/api/v1/permissions``, ``/api/v1/marketplace`` (Milestone 9 Task
Group E). Real, in-process ``TestClient`` against a real temp-file
SQLite database and a real, temp-dir-backed Plugin Platform stack --
matches ``test_runtime_ws_route.py``'s own established pattern, no
mocked network."""

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
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def _write_plugin(root: Path, plugin_id: str, *, permissions=()) -> Path:
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
        "    async def on_load(self, context) -> None: pass\n"
        "    async def on_start(self) -> None: pass\n"
        "    async def on_stop(self) -> None: pass\n",
        encoding="utf-8",
    )
    return plugin_dir


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_list_plugins_requires_auth(client) -> None:
    assert client.get("/api/v1/plugins").status_code == 401


def test_list_plugins_rejects_malformed_scheme(client) -> None:
    response = client.get("/api/v1/plugins", headers={"Authorization": "Basic xyz"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Plugin registry routes
# ---------------------------------------------------------------------------
def test_list_plugins_empty_envelope(client, auth_headers) -> None:
    response = client.get("/api/v1/plugins", headers=auth_headers)
    assert response.status_code == 200
    assert response.json() == {"data": [], "meta": {"count": 0}}


def test_install_then_list_then_get(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world")

    install = client.post(
        "/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers
    )
    assert install.status_code == 201
    assert install.json()["data"]["plugin_id"] == "hello-world"

    listing = client.get("/api/v1/plugins", headers=auth_headers)
    assert listing.json()["meta"]["count"] == 1

    detail = client.get("/api/v1/plugins/hello-world", headers=auth_headers)
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["plugin_id"] == "hello-world"
    assert body["state"] == "running"
    assert body["healthy"] is True


def test_get_unknown_plugin_returns_404(client, auth_headers) -> None:
    response = client.get("/api/v1/plugins/ghost", headers=auth_headers)
    assert response.status_code == 404


def test_disable_then_enable_round_trip(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world")
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    disable = client.post("/api/v1/plugins/hello-world/disable", headers=auth_headers)
    assert disable.status_code == 200
    assert disable.json()["data"]["disabled"] is True

    enable = client.post("/api/v1/plugins/hello-world/enable", headers=auth_headers)
    assert enable.status_code == 200
    assert enable.json()["data"]["enabled"] is True


def test_uninstall_removes_plugin(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world")
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    response = client.post("/api/v1/plugins/hello-world/uninstall", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["uninstalled"] is True
    assert client.get("/api/v1/plugins/hello-world", headers=auth_headers).status_code == 404


def test_install_from_missing_path_returns_422(client, auth_headers) -> None:
    response = client.post(
        "/api/v1/plugins/install",
        json={"source_path": str(client.tmp_path / "does-not-exist")},
        headers=auth_headers,
    )
    assert response.status_code == 422


def test_update_plugin(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world")
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    new_source = client.tmp_path / "staged-v2" / "hello-world"
    new_source.mkdir(parents=True)
    manifest = {
        "name": "hello-world",
        "display_name": "Hello World",
        "version": "2.0.0",
        "entry_point": "plugin:HelloPlugin",
    }
    (new_source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (new_source / "plugin.py").write_text(
        "class HelloPlugin:\n"
        "    async def on_load(self, context) -> None: pass\n"
        "    async def on_start(self) -> None: pass\n"
        "    async def on_stop(self) -> None: pass\n",
        encoding="utf-8",
    )

    response = client.post(
        "/api/v1/plugins/hello-world/update",
        json={"source_path": str(new_source)},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["updated"] is True

    detail = client.get("/api/v1/plugins/hello-world", headers=auth_headers).json()["data"]
    assert detail["version"] == "2.0.0"


# ---------------------------------------------------------------------------
# Permission management routes
# ---------------------------------------------------------------------------
def test_permission_workflow_pending_then_grant(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world", permissions=["network"])
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    pending = client.get("/api/v1/permissions/pending", headers=auth_headers).json()["data"]
    assert {"plugin_id": "hello-world", "scope": "network", "state": "pending"} in pending

    perms = client.get("/api/v1/plugins/hello-world/permissions", headers=auth_headers).json()[
        "data"
    ]
    assert perms[0]["state"] == "pending"

    grant = client.post(
        "/api/v1/plugins/hello-world/permissions/network/grant", headers=auth_headers
    )
    assert grant.status_code == 200
    assert grant.json()["data"]["state"] == "granted"

    perms_after = client.get(
        "/api/v1/plugins/hello-world/permissions", headers=auth_headers
    ).json()["data"]
    assert perms_after[0]["state"] == "granted"


def test_deny_and_revoke_permission(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world", permissions=["network"])
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)

    deny = client.post("/api/v1/plugins/hello-world/permissions/network/deny", headers=auth_headers)
    assert deny.json()["data"]["state"] == "denied"

    revoke = client.post(
        "/api/v1/plugins/hello-world/permissions/network/revoke", headers=auth_headers
    )
    assert revoke.json()["data"]["state"] == "pending"


def test_audit_log_records_grant(client, auth_headers) -> None:
    source = _write_plugin(client.tmp_path / "staged", "hello-world", permissions=["network"])
    client.post("/api/v1/plugins/install", json={"source_path": str(source)}, headers=auth_headers)
    client.post("/api/v1/plugins/hello-world/permissions/network/grant", headers=auth_headers)

    audit = client.get("/api/v1/permissions/audit-log", headers=auth_headers).json()["data"]
    actions = [e["action"] for e in audit if e["plugin_id"] == "hello-world"]
    assert "granted" in actions


# ---------------------------------------------------------------------------
# Marketplace routes
# ---------------------------------------------------------------------------
def test_marketplace_browse_empty_without_index(client, auth_headers) -> None:
    response = client.get("/api/v1/marketplace", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


def _write_marketplace_index(client) -> None:
    from jarvis.core.config import paths as _paths

    settings = client.container.settings()
    index_path = _paths.config_dir(settings.resolved_data_dir) / "marketplace_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(
            {
                "plugins": [
                    {
                        "name": "weather-widget",
                        "display_name": "Weather Widget",
                        "description": "Shows the weather.",
                        "author": "JARVIS Team",
                        "versions": ["1.0.0"],
                        "category": "widgets",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_marketplace_browse_and_get_and_search(client, auth_headers) -> None:
    _write_marketplace_index(client)

    browse = client.get("/api/v1/marketplace", headers=auth_headers)
    assert browse.status_code == 200
    assert len(browse.json()["data"]) == 1

    get = client.get("/api/v1/marketplace/weather-widget", headers=auth_headers)
    assert get.status_code == 200
    assert get.json()["data"]["display_name"] == "Weather Widget"

    search = client.get("/api/v1/marketplace/search", params={"q": "weather"}, headers=auth_headers)
    assert len(search.json()["data"]) == 1

    categories = client.get("/api/v1/marketplace/categories", headers=auth_headers)
    assert categories.json()["data"] == ["widgets"]


def test_marketplace_unknown_listing_404(client, auth_headers) -> None:
    response = client.get("/api/v1/marketplace/ghost", headers=auth_headers)
    assert response.status_code == 404


def test_marketplace_rate_and_get_reviews(client, auth_headers) -> None:
    _write_marketplace_index(client)

    rate = client.post(
        "/api/v1/marketplace/weather-widget/reviews",
        json={"reviewer": "alice", "stars": 5, "comment": "Great!"},
        headers=auth_headers,
    )
    assert rate.status_code == 201
    assert rate.json()["data"]["average_rating"] == 5.0

    reviews = client.get("/api/v1/marketplace/weather-widget/reviews", headers=auth_headers)
    assert reviews.status_code == 200
    assert len(reviews.json()["data"]) == 1
    assert reviews.json()["meta"]["average_rating"] == 5.0


def test_marketplace_rate_out_of_range_returns_422(client, auth_headers) -> None:
    _write_marketplace_index(client)
    response = client.post(
        "/api/v1/marketplace/weather-widget/reviews",
        json={"reviewer": "alice", "stars": 6},
        headers=auth_headers,
    )
    assert response.status_code == 422
