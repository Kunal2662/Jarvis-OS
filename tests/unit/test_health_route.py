"""Health/readiness route tests -- Milestone 0's router, revisited by
the Aug 2026 backlog pass to close §15's "health router mount prefix
mismatch" item.

``docs/ARCHITECTURE.md`` §5/§6 have always documented
``/api/v1/health``; the router has answered on ``/api/health`` since
M0. Both are now served, and these tests pin that: adding the
documented path is the fix, and *removing* the original would break
external monitoring that has been polling it for the whole project's
life.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from jarvis.__version__ import __version__


@pytest.fixture
def client():
    from jarvis.core.config.settings import Settings
    from jarvis.infrastructure.api.fastapi_server import create_app

    # No container: the health router is mounted unconditionally, which
    # is what lets it answer before the runtime is wired.
    with TestClient(create_app(Settings(), None)) as test_client:
        yield test_client


@pytest.mark.parametrize("path", ["/api/health", "/api/v1/health"])
def test_health_is_served_on_both_paths(client, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


@pytest.mark.parametrize("path", ["/api/ready", "/api/v1/ready"])
def test_ready_is_served_on_both_paths(client, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "version": __version__}


def test_both_paths_return_identical_bodies(client) -> None:
    """One router, mounted twice -- not two implementations that could
    drift apart."""
    assert client.get("/api/health").json() == client.get("/api/v1/health").json()
    assert client.get("/api/ready").json() == client.get("/api/v1/ready").json()


def test_health_stays_outside_the_envelope(client) -> None:
    """§5's ``{data, meta}`` envelope is for resource routes. A liveness
    probe is polled by tooling expecting a flat, minimal body, and
    wrapping it would buy consistency with resources it is not one
    of."""
    body = client.get("/api/v1/health").json()

    assert "data" not in body
    assert set(body) == {"status", "version"}
