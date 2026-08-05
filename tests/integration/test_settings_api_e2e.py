"""Settings API end-to-end -- Milestone 8 Phase 2.

Real DI container, real REST app, real ``Settings``. The point of these
tests is not that a route returns 200 -- it is that the route cannot leak
a secret. ``SettingsService.snapshot()`` publishes
``integrations.clients`` verbatim, and that dict holds OAuth client
secrets in plain strings that pydantic's ``SecretStr`` redaction never
covered, because Task Group E introduced it as a plain
``dict[str, dict[str, str]]``. Before this phase nothing crossed a
process boundary with it, so the leak was latent; adding a settings API
is exactly the change that makes it live.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


@pytest.fixture
def client(tmp_path: Path):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"

    # A real secret in every shape the tree can hold one: a pydantic
    # SecretStr field, and the plain-dict OAuth client credentials that
    # SecretStr does not reach. `SecretStr(...)` rather than a bare
    # string because pydantic does not validate on assignment -- a raw
    # `str` here would be stored as-is and blow up in the serialiser,
    # testing my fixture rather than the route.
    settings.openai.api_key = SecretStr("sk-live-do-not-leak")
    settings.integrations.clients = {
        "google": {
            "client_id": "1234.apps.googleusercontent.com",
            "client_secret": "GOCSPX-do-not-leak",
        }
    }
    container.settings.override(settings)

    database = container.database()
    asyncio.run(database.initialize())

    app = create_app(settings, container)

    with TestClient(app) as test_client:
        yield test_client

    asyncio.run(database.dispose())


@pytest.fixture
def auth(client):
    session = client.post("/api/v1/sessions", json={}).json()["data"]
    return {"Authorization": f"Bearer {session['session_id']}"}


def test_requires_authentication(client):
    assert client.get("/api/v1/settings").status_code == 401


def test_returns_the_tree_in_the_standard_envelope(client, auth):
    response = client.get("/api/v1/settings", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {"data", "meta"}
    assert body["meta"]["read_only"] is True
    assert isinstance(body["meta"]["writable_keys"], list)
    assert "ui" in body["data"]


def test_no_secret_survives_the_round_trip(client, auth):
    """The whole point of the route: nothing secret crosses the boundary."""
    raw = client.get("/api/v1/settings", headers=auth).text

    assert "sk-live-do-not-leak" not in raw
    assert "GOCSPX-do-not-leak" not in raw


def test_non_secret_neighbours_survive(client, auth):
    """Redaction is by key name, so it must not swallow the whole dict.

    ``client_id`` is *not* a secret -- an OAuth client id is public by
    design -- and a settings screen that cannot show which client is
    configured is useless. This is the test that stops a future
    "redact anything under `clients`" simplification.
    """
    data = client.get("/api/v1/settings", headers=auth).json()["data"]

    assert data["integrations"]["clients"]["google"]["client_id"] == (
        "1234.apps.googleusercontent.com"
    )
    assert data["integrations"]["clients"]["google"]["client_secret"] != "GOCSPX-do-not-leak"


def test_single_key_read(client, auth):
    response = client.get("/api/v1/settings/ui.theme", headers=auth)

    assert response.status_code == 200
    assert response.json()["data"] == {"key": "ui.theme", "value": "jarvis"}


def test_single_key_cannot_be_used_to_fetch_a_secret(client, auth):
    """The per-key route reads the *public* snapshot, not the raw one."""
    response = client.get("/api/v1/settings/openai.api_key", headers=auth)

    assert response.status_code == 200
    assert "sk-live-do-not-leak" not in response.text

    nested = client.get("/api/v1/settings/integrations.clients", headers=auth)
    assert "GOCSPX-do-not-leak" not in nested.text


def test_unknown_key_is_404_not_500(client, auth):
    response = client.get("/api/v1/settings/nope.nothing", headers=auth)

    assert response.status_code == 404
    assert "nope.nothing" in response.json()["detail"]


def test_walking_into_a_scalar_is_404(client, auth):
    assert client.get("/api/v1/settings/ui.theme.deeper", headers=auth).status_code == 404


def test_no_write_route_exists(client, auth):
    """Writing a setting means writing ``.env``; that is not this phase's.

    Asserted rather than assumed, so a later addition is a deliberate act
    with this test to update -- not something that arrives unnoticed.
    """
    put = client.put("/api/v1/settings/ui.theme", json={"value": "x"}, headers=auth)
    assert put.status_code in (404, 405)
    assert client.post("/api/v1/settings", json={}, headers=auth).status_code in (404, 405)


def test_response_is_json_serialisable_all_the_way_down(client, auth):
    """``model_dump(mode="json")`` -- no Path or datetime escapes as an object."""
    json.dumps(client.get("/api/v1/settings", headers=auth).json())
