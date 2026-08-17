"""Device Diagnostics REST tests -- Milestone 12 Developer Tools
(Device Diagnostics Slice).

Against the real FastAPI app and the real DI container, matching every
other M12 devtools route test's pattern. No permission grant is
required to *reach* these routes -- there is no `PermissionModel` gate
on `GET /devtools/devices/{id}/diagnostics` itself (Logic Contract
§8); permission grants are used here only to exercise the diagnostic's
own *reported* permission state for a device's owning principal.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


@pytest.fixture
def fake_connector():
    from tests.fakes.fake_device_connector import FakeDeviceConnector

    return FakeDeviceConnector()


@pytest.fixture
def client(tmp_path: Path, fake_connector):
    from fastapi.testclient import TestClient

    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
    from jarvis.core.di.container import Container
    from jarvis.infrastructure.api.fastapi_server import create_app

    container = Container()
    settings = Settings(data_dir=str(tmp_path / "data"))
    settings.db.url = f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}"
    container.settings.override(settings)

    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    container.connectivity_registry.override(registry)

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


def _home(client, auth, name: str = "Primary Residence") -> str:
    response = client.post("/api/v1/homes", json={"name": name}, headers=auth)
    assert response.status_code == 201
    return response.json()["data"]["id"]


def _connect(client, auth) -> None:
    client.post(
        "/api/v1/connectivity/connectors/home_assistant/connect", json={"config": {}}, headers=auth
    )


def _discover(client, auth, fake_connector, home_id: str, devices) -> list[dict]:
    fake_connector.devices = devices
    response = client.post(
        "/api/v1/connectivity/discover",
        json={"connector_type": "home_assistant", "home_id": home_id},
        headers=auth,
    )
    assert response.status_code == 200
    return response.json()["data"]


def _bare_device(client, auth, home_id: str, device_type: str, name: str = "X") -> dict:
    """A device created directly (no connector, no discovery) -- used
    for the "no recorded connector" connectivity-failure case."""
    response = client.post(
        "/api/v1/devices",
        json={"home_id": home_id, "name": name, "device_type": device_type},
        headers=auth,
    )
    assert response.status_code == 201
    return response.json()["data"]


def _diagnostics(client, auth, device_id: str):
    return client.get(f"/api/v1/devtools/devices/{device_id}/diagnostics", headers=auth)


def _grant(client, auth, principal: str) -> None:
    response = client.post(
        f"/api/v1/plugins/{principal}/permissions/smart_home/grant", headers=auth
    )
    assert response.status_code == 200


# --- Auth ------------------------------------------------------------------------


def test_route_requires_a_session(client) -> None:
    assert client.get("/api/v1/devtools/devices/x/diagnostics").status_code == 401


def test_no_permission_grant_needed_to_reach_the_route(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")
    response = _diagnostics(client, auth, device["id"])
    assert response.status_code == 200


# --- Happy path: every supported device_type -------------------------------------


@pytest.mark.parametrize(
    "device_type,expected_principal",
    [
        ("light", "core:smart_lighting"),
        ("switch", "core:smart_switch"),
        ("lock", "core:smart_locks"),
        ("sensor", "core:sensors"),
        ("thermostat", "core:thermostats"),
    ],
)
def test_happy_path_known_categories(
    client, auth, fake_connector, device_type: str, expected_principal: str
) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState, DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    external_id = f"{device_type}.x"
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id=external_id, name="X", device_type=device_type)],
    )
    device_id = discovered[0]["id"]
    fake_connector.states[external_id] = DeviceState(
        external_id=external_id, status="on", attributes={"foo": "bar"}
    )

    response = _diagnostics(client, auth, device_id)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"data", "meta"}
    assert set(body["data"]) == {"device", "connectivity", "permission"}
    assert body["data"]["device"]["device_type"] == device_type
    assert body["data"]["connectivity"]["read_succeeded"] is True
    assert body["data"]["connectivity"]["status"] == "on"
    assert body["data"]["connectivity"]["attributes"] == {"foo": "bar"}
    assert body["data"]["connectivity"]["connector_type"] == "home_assistant"
    assert body["data"]["permission"]["principal"] == expected_principal
    assert body["data"]["permission"]["scope"] == "smart_home"
    assert body["meta"]["device_type"] == device_type


def test_happy_path_appliance_and_camera(client, auth) -> None:
    home_id = _home(client, auth)
    appliance = _bare_device(client, auth, home_id, "appliance")
    camera = _bare_device(client, auth, home_id, "camera")

    r1 = _diagnostics(client, auth, appliance["id"])
    r2 = _diagnostics(client, auth, camera["id"])

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["permission"]["principal"] is None
    assert r2.json()["data"]["permission"]["principal"] is None


# --- Device section ----------------------------------------------------------------


def test_device_section_identity_fields(client, auth, fake_connector) -> None:
    """No live read needed for this test -- only the persisted device
    row's own identity fields are under test, so a bare (never
    discovered/connected) device is the simplest fixture."""
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light", name="Living Room Light")

    body = _diagnostics(client, auth, device["id"]).json()["data"]["device"]

    assert body["id"] == device["id"]
    assert body["name"] == "Living Room Light"
    assert body["device_type"] == "light"
    assert body["home_id"] == home_id
    assert body["room_id"] is None
    assert body["external_id"] is None
    assert body["last_seen_at"] is None


def test_device_section_never_exposes_metadata_json(client, auth) -> None:
    home_id = _home(client, auth)
    device = client.post(
        "/api/v1/devices",
        json={
            "home_id": home_id,
            "name": "X",
            "device_type": "light",
            "metadata": {"connector_type": "home_assistant", "secret_field": "sh-do-not-leak"},
        },
        headers=auth,
    ).json()["data"]

    response = _diagnostics(client, auth, device["id"])

    assert "metadata_json" not in response.text
    assert "secret_field" not in response.text
    assert "sh-do-not-leak" not in response.text


# --- Connectivity: failure modes ---------------------------------------------------


def test_connectivity_no_recorded_connector(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")

    response = _diagnostics(client, auth, device["id"])

    assert response.status_code == 200
    conn = response.json()["data"]["connectivity"]
    assert conn["read_succeeded"] is False
    assert conn["connector_type"] is None
    assert conn["read_error"] == "device has no recorded connector"
    # Rest of the diagnostic is still present.
    assert response.json()["data"]["device"]["id"] == device["id"]
    assert response.json()["data"]["permission"]["principal"] == "core:smart_lighting"


def test_connectivity_connector_not_connected(client, auth, fake_connector) -> None:
    """Device has a recorded connector_type, but that connector was
    never `connect()`-ed -- `read_raw_state` raises
    `ConnectorNotConnectedError`, caught and reported, not a 500."""
    from jarvis.core.interfaces.connectivity import DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="light.x", name="X", device_type="light")],
    )
    device_id = discovered[0]["id"]
    # Disconnect the connector after discovery so the device still has
    # connector_type="home_assistant" recorded but no live connection.
    client.post("/api/v1/connectivity/connectors/home_assistant/disconnect", headers=auth)

    response = _diagnostics(client, auth, device_id)

    assert response.status_code == 200
    conn = response.json()["data"]["connectivity"]
    assert conn["read_succeeded"] is False
    assert conn["connector_type"] == "home_assistant"
    assert conn["read_error"]


def test_connectivity_unavailable_status_is_a_successful_read(client, auth, fake_connector) -> None:
    """A device reporting `status="unavailable"` is still a
    *successful* read -- `read_succeeded` means "the read attempt
    completed," not "the device is online" (Logic Contract §5)."""
    from jarvis.core.interfaces.connectivity import DeviceState, DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="light.x", name="X", device_type="light")],
    )
    device_id = discovered[0]["id"]
    fake_connector.states["light.x"] = DeviceState(
        external_id="light.x", status="unavailable", attributes={}
    )

    response = _diagnostics(client, auth, device_id)

    conn = response.json()["data"]["connectivity"]
    assert conn["read_succeeded"] is True
    assert conn["status"] == "unavailable"
    assert conn["read_error"] is None


# --- Permission ----------------------------------------------------------------------


def test_permission_state_pending_by_default(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "lock")

    body = _diagnostics(client, auth, device["id"]).json()["data"]["permission"]

    assert body["principal"] == "core:smart_locks"
    assert body["state"] == "pending"


def test_permission_state_granted(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "sensor")
    # Declaring the principal requires the owning service to exist --
    # grant the scope directly; PermissionModel.declare() happens
    # lazily the first time SensorService is constructed, which the DI
    # container already does at startup, so the principal is already
    # declared (PENDING) before this grant call.
    _grant(client, auth, "core:sensors")

    body = _diagnostics(client, auth, device["id"]).json()["data"]["permission"]

    assert body["state"] == "granted"


def test_permission_state_denied(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "switch")
    client.post("/api/v1/plugins/core:smart_switch/permissions/smart_home/deny", headers=auth)

    body = _diagnostics(client, auth, device["id"]).json()["data"]["permission"]

    assert body["state"] == "denied"


def test_permission_appliance_reports_explanatory_detail(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "appliance")

    body = _diagnostics(client, auth, device["id"]).json()["data"]["permission"]

    assert body["principal"] is None
    assert body["state"] is None
    assert "multiple principals" in body["detail"]


def test_permission_unknown_device_type_reports_explanatory_detail(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "other")

    body = _diagnostics(client, auth, device["id"]).json()["data"]["permission"]

    assert body["principal"] is None
    assert "no dedicated permission principal" in body["detail"]


# --- Security / redaction -----------------------------------------------------------


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "token",
        "access_token",
        "password",
        "api_key",
        "apikey",
        "secret",
        "client_secret",
        "auth_header",
        "mqtt_credential",
    ],
)
def test_sensitive_attribute_values_are_redacted(
    client, auth, fake_connector, sensitive_key: str
) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState, DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="light.x", name="X", device_type="light")],
    )
    device_id = discovered[0]["id"]
    fake_connector.states["light.x"] = DeviceState(
        external_id="light.x",
        status="on",
        attributes={sensitive_key: "sh-real-secret-value", "brightness": 50},
    )

    response = _diagnostics(client, auth, device_id)

    attrs = response.json()["data"]["connectivity"]["attributes"]
    assert attrs[sensitive_key] == "<redacted>"
    assert attrs["brightness"] == 50
    assert "sh-real-secret-value" not in response.text


def test_non_sensitive_attributes_pass_through_verbatim(client, auth, fake_connector) -> None:
    from jarvis.core.interfaces.connectivity import DeviceState, DiscoveredDevice

    home_id = _home(client, auth)
    _connect(client, auth)
    discovered = _discover(
        client,
        auth,
        fake_connector,
        home_id,
        [DiscoveredDevice(external_id="light.x", name="X", device_type="light")],
    )
    device_id = discovered[0]["id"]
    fake_connector.states["light.x"] = DeviceState(
        external_id="light.x",
        status="on",
        attributes={"brightness": 80, "color_temp_kelvin": 3000},
    )

    attrs = _diagnostics(client, auth, device_id).json()["data"]["connectivity"]["attributes"]

    assert attrs == {"brightness": 80, "color_temp_kelvin": 3000}


# --- REST ------------------------------------------------------------------------------


def test_unknown_device_is_404(client, auth) -> None:
    response = _diagnostics(client, auth, "no-such-device")
    assert response.status_code == 404


def test_response_uses_the_documented_envelope(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")

    response = _diagnostics(client, auth, device["id"])

    assert set(response.json()) == {"data", "meta"}


def test_no_mutation_endpoints_exist(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")
    path = f"/api/v1/devtools/devices/{device['id']}/diagnostics"

    for method in ("post", "put", "delete", "patch"):
        assert getattr(client, method)(path, headers=auth).status_code in (404, 405)


def test_no_duplicate_or_alternate_routes(client, auth) -> None:
    home_id = _home(client, auth)
    device = _bare_device(client, auth, home_id, "light")
    for path in (
        f"/api/v1/devtools/diagnostics/{device['id']}",
        "/api/v1/devtools/devices/diagnostics",
        f"/api/v1/devtools/devices/{device['id']}/health",
    ):
        assert client.get(path, headers=auth).status_code == 404


# --- Architecture guards --------------------------------------------------------------


def _code_without_docstrings(source: str) -> str:
    import ast

    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
            if not node.body:
                node.body.append(ast.Pass())
    return ast.unparse(tree)


def _devtools_route_code() -> str:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    return _code_without_docstrings(inspect.getsource(devtools_module))


def test_is_granted_never_called_by_diagnostics() -> None:
    """`PermissionModel.state()` only -- `is_granted()` has a
    `_audit_add("denied_check")` side effect a passive diagnostic read
    must never trigger (Logic Contract §7)."""
    source = _devtools_route_code()
    assert "is_granted" not in source


def test_no_eventbus_scheduler_analytics_memory_reference() -> None:
    source = _devtools_route_code()
    for forbidden in ("EventBus", "event_bus", "Scheduler", "Analytics", "MemoryService"):
        assert forbidden not in source


def test_device_diagnostics_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.infrastructure.api.routes import devtools as devtools_module

    import_lines = [
        line
        for line in inspect.getsource(devtools_module).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "ConnectorCredentialStore" not in joined


def test_device_type_principal_table_is_exactly_five_entries() -> None:
    from jarvis.infrastructure.api.routes.devtools import _DEVICE_TYPE_PRINCIPALS

    assert _DEVICE_TYPE_PRINCIPALS == {
        "light": "core:smart_lighting",
        "switch": "core:smart_switch",
        "lock": "core:smart_locks",
        "sensor": "core:sensors",
        "thermostat": "core:thermostats",
    }


def test_no_agent_tool_for_diagnostics() -> None:
    """Purely developer-facing -- no end-user/AI Home Assistant use
    case exists for this capability (Logic Contract §10)."""
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry()
    assert "get_device_diagnostics" not in {t.name for t in tools}
