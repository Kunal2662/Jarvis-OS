"""Provider REST route tests -- Milestone 10.5 Task Group C,
deliverables 9 and 10. Real ``TestClient`` against the real DI
container."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


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
def auth_headers(client):
    session = client.post("/api/v1/sessions", json={}).json()
    return {"Authorization": f"Bearer {session['session_id']}"}


def _install(container, provider_id: str = "demo", **meta_kwargs):
    from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata

    metadata = ProviderMetadata(
        name=meta_kwargs.pop("name", "Demo"),
        transport=meta_kwargs.pop("transport", "stdio"),
        capabilities=meta_kwargs.pop("capabilities", ("echo",)),
        required_permissions=meta_kwargs.pop("required_permissions", ("agent_tools",)),
        **meta_kwargs,
    )
    config = ProviderConfig(options={"command": "python"})
    return asyncio.run(container.mcp_provider_manager().install(provider_id, metadata, config))


# --- Auth ----------------------------------------------------------------------


def test_providers_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/providers").status_code == 401


def test_provider_detail_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/providers/demo").status_code == 401


def test_provider_health_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/providers/demo/health").status_code == 401


def test_provider_metadata_requires_auth(client) -> None:
    assert client.get("/api/v1/mcp/providers/demo/metadata").status_code == 401


# --- Listing / discovery -------------------------------------------------------


def test_providers_starts_empty(client, auth_headers) -> None:
    body = client.get("/api/v1/mcp/providers", headers=auth_headers).json()

    assert body["data"] == []
    assert body["meta"] == {"count": 0, "total": 0}


def test_providers_lists_an_installed_provider(client, auth_headers) -> None:
    _install(client.container)

    body = client.get("/api/v1/mcp/providers", headers=auth_headers).json()

    assert body["meta"]["count"] == 1
    assert body["data"][0]["provider_id"] == "demo"
    assert body["data"][0]["state"] == "registered"
    assert body["data"][0]["metadata"]["capabilities"] == ["echo"]


def test_providers_discovery_filters_are_exposed_as_query_params(client, auth_headers) -> None:
    _install(client.container, "alpha", transport="stdio", capabilities=("echo",))
    _install(client.container, "beta", transport="http", capabilities=("fetch",))

    by_transport = client.get("/api/v1/mcp/providers?transport=http", headers=auth_headers).json()
    by_capability = client.get("/api/v1/mcp/providers?capability=echo", headers=auth_headers).json()

    assert [p["provider_id"] for p in by_transport["data"]] == ["beta"]
    assert [p["provider_id"] for p in by_capability["data"]] == ["alpha"]
    # 'total' always reports the whole registry, so a filtered view
    # still says how much it filtered out of.
    assert by_transport["meta"]["total"] == 2


def test_providers_filters_combine_with_and(client, auth_headers) -> None:
    _install(client.container, "alpha", transport="stdio", capabilities=("echo",))

    body = client.get(
        "/api/v1/mcp/providers?transport=http&capability=echo", headers=auth_headers
    ).json()

    assert body["data"] == []


# --- Detail / health / metadata ------------------------------------------------


def test_provider_detail_reports_permissions(client, auth_headers) -> None:
    _install(client.container)

    body = client.get("/api/v1/mcp/providers/demo", headers=auth_headers).json()

    assert body["data"]["provider_id"] == "demo"
    assert body["data"]["pending_permissions"] == ["agent_tools"]
    assert body["data"]["granted_permissions"] == []


def test_provider_health_reports_unhealthy_before_connect(client, auth_headers) -> None:
    _install(client.container)

    response = client.get("/api/v1/mcp/providers/demo/health", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["data"]["healthy"] is False
    assert response.json()["meta"]["healthy"] is False


def test_provider_metadata_returns_the_declaration_only(client, auth_headers) -> None:
    _install(client.container, author="someone", description="d")

    body = client.get("/api/v1/mcp/providers/demo/metadata", headers=auth_headers).json()

    assert body["data"]["name"] == "Demo"
    assert body["data"]["author"] == "someone"
    assert body["data"]["transport"] == "stdio"
    # A declaration, not live state.
    assert "state" not in body["data"]


@pytest.mark.parametrize("suffix", ["", "/health", "/metadata"])
def test_unknown_provider_is_404(client, auth_headers, suffix: str) -> None:
    response = client.get(f"/api/v1/mcp/providers/nope{suffix}", headers=auth_headers)
    assert response.status_code == 404


def test_option_values_are_never_exposed(client, auth_headers) -> None:
    """Option values will carry credentials once M11's providers exist."""
    from jarvis.core.mcp.providers.metadata import ProviderConfig, ProviderMetadata

    asyncio.run(
        client.container.mcp_provider_manager().install(
            "secretive",
            ProviderMetadata(name="Secretive"),
            ProviderConfig(options={"token": "super-secret-value"}),
        )
    )

    body = client.get("/api/v1/mcp/providers", headers=auth_headers).text

    assert "super-secret-value" not in body
    assert "token" in body  # the key name is still reported


# --- DI ------------------------------------------------------------------------


def test_registry_and_manager_are_singletons(client) -> None:
    container = client.container

    assert container.mcp_provider_registry() is container.mcp_provider_registry()
    assert container.mcp_provider_manager() is container.mcp_provider_manager()
    # The manager wraps the same registry instance the route reads.
    assert container.mcp_provider_manager().registry is container.mcp_provider_registry()
