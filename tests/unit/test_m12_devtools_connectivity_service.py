"""DevtoolsConnectivityService tests -- Milestone 12 Developer Tools
(Connectivity / Integration Health Slice).

Real ``SmartHomeService``/``ConnectivityService``/
``ConnectorFactoryRegistry`` throughout, real (temp-file) SQLite,
matching every other M12 service test's own "fakes, not mocks"
discipline -- only the connector itself is faked
(``FakeDeviceConnector``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.devtools_connectivity_service import DevtoolsConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from tests.fakes.fake_device_connector import FakeDeviceConnector


def _settings(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("JARVIS_DB_URL", f"sqlite+aiosqlite:///{tmp_path / 'jarvis.db'}")

    from jarvis.core.config import settings as settings_mod

    settings_mod.load_settings.cache_clear()  # type: ignore[attr-defined]
    return settings_mod.load_settings()


@pytest.fixture
async def db(tmp_path: Path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)
    from jarvis.infrastructure.database.sqlite_client import SQLiteDatabase

    database = SQLiteDatabase(settings.db)
    await database.initialize()
    try:
        yield database
    finally:
        await database.dispose()


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def smart_home(db, bus: EventBus) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=bus)


@pytest.fixture
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def registry(fake_connector: FakeDeviceConnector) -> ConnectorFactoryRegistry:
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: fake_connector)
    return reg


@pytest.fixture
def connectivity(
    registry: ConnectorFactoryRegistry, smart_home: SmartHomeService, bus: EventBus
) -> ConnectivityService:
    return ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)


@pytest.fixture
def service(
    connectivity: ConnectivityService,
    registry: ConnectorFactoryRegistry,
    smart_home: SmartHomeService,
) -> DevtoolsConnectivityService:
    return DevtoolsConnectivityService(
        connectivity=connectivity, connectivity_registry=registry, smart_home=smart_home
    )


# --- Connector status --------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_connectors_registered_is_empty_list(smart_home: SmartHomeService) -> None:
    empty_registry = ConnectorFactoryRegistry()
    bus = EventBus()
    connectivity = ConnectivityService(
        registry=empty_registry, smart_home=smart_home, event_bus=bus
    )
    svc = DevtoolsConnectivityService(
        connectivity=connectivity, connectivity_registry=empty_registry, smart_home=smart_home
    )

    rows = await svc.get_connector_status()

    assert rows == []


@pytest.mark.asyncio
async def test_registered_but_never_connected_reports_false(
    service: DevtoolsConnectivityService,
) -> None:
    rows = await service.get_connector_status()

    assert rows == [{"connector_type": "home_assistant", "registered": True, "connected": False}]


@pytest.mark.asyncio
async def test_connected_connector_reports_true(
    service: DevtoolsConnectivityService, connectivity: ConnectivityService
) -> None:
    await connectivity.connect("home_assistant")

    rows = await service.get_connector_status()

    assert rows == [{"connector_type": "home_assistant", "registered": True, "connected": True}]


@pytest.mark.asyncio
async def test_disconnected_after_connect_reports_false_again(
    service: DevtoolsConnectivityService, connectivity: ConnectivityService
) -> None:
    await connectivity.connect("home_assistant")
    await connectivity.disconnect("home_assistant")

    rows = await service.get_connector_status()

    # Disconnected connectors are removed from ConnectivityService's own
    # internal map entirely (`disconnect` deletes the entry) -- but the
    # type remains *registered* (a factory still exists), so it must
    # still appear here, now reporting connected=False.
    assert rows == [{"connector_type": "home_assistant", "registered": True, "connected": False}]


@pytest.mark.asyncio
async def test_multiple_registered_connectors(smart_home: SmartHomeService) -> None:
    ha_fake = FakeDeviceConnector()
    mqtt_fake = FakeDeviceConnector()
    mqtt_fake.connector_type = "mqtt"
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: ha_fake)
    reg.register("mqtt", lambda config: mqtt_fake)
    bus = EventBus()
    connectivity = ConnectivityService(registry=reg, smart_home=smart_home, event_bus=bus)
    svc = DevtoolsConnectivityService(
        connectivity=connectivity, connectivity_registry=reg, smart_home=smart_home
    )
    await connectivity.connect("home_assistant")

    rows = await svc.get_connector_status()

    assert {r["connector_type"] for r in rows} == {"home_assistant", "mqtt"}
    by_type = {r["connector_type"]: r for r in rows}
    assert by_type["home_assistant"]["connected"] is True
    assert by_type["mqtt"]["connected"] is False
    assert all(r["registered"] is True for r in rows)


# --- Device health -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_health_unknown_home_raises(service: DevtoolsConnectivityService) -> None:
    with pytest.raises(ServiceError, match="does not exist"):
        await service.get_device_health("no-such-home")


@pytest.mark.asyncio
async def test_device_health_no_homes_is_empty_list(
    service: DevtoolsConnectivityService,
) -> None:
    rows = await service.get_device_health()

    assert rows == []


@pytest.mark.asyncio
async def test_device_health_zero_devices(
    service: DevtoolsConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")

    rows = await service.get_device_health(home.id)

    assert rows == [
        {
            "home_id": home.id,
            "room_count": 0,
            "zone_count": 0,
            "device_count": 0,
            "paired_device_count": 0,
            "offline_device_count": 0,
            "unreachable_device_count": 0,
        }
    ]


@pytest.mark.asyncio
async def test_device_health_reflects_real_counts(
    service: DevtoolsConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    await smart_home.create_room(home.id, "Kitchen")
    paired = await smart_home.register_discovered_device(
        home.id, "Light", device_type="light", external_id="light.kitchen"
    )
    await smart_home.pair_device(paired.id)
    offline_device = await smart_home.register_discovered_device(
        home.id, "Lock", device_type="lock", external_id="lock.front"
    )
    await smart_home.pair_device(offline_device.id)
    await smart_home.report_device_state(offline_device.id, status="offline")

    rows = await service.get_device_health(home.id)

    row = rows[0]
    assert row["device_count"] == 2
    assert row["room_count"] == 1
    assert row["paired_device_count"] == 1
    assert row["offline_device_count"] == 1
    assert row["unreachable_device_count"] == 0


@pytest.mark.asyncio
async def test_device_health_no_home_id_lists_every_home(
    service: DevtoolsConnectivityService, smart_home: SmartHomeService
) -> None:
    home_a = await smart_home.create_home("Home A")
    home_b = await smart_home.create_home("Home B")

    rows = await service.get_device_health()

    assert {r["home_id"] for r in rows} == {home_a.id, home_b.id}


# --- Combined overview ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_combines_connectors_and_homes(
    service: DevtoolsConnectivityService,
    connectivity: ConnectivityService,
    smart_home: SmartHomeService,
) -> None:
    await connectivity.connect("home_assistant")
    home = await smart_home.create_home("Primary Residence")

    overview = await service.get_overview(home.id)

    assert overview["connectors"] == [
        {"connector_type": "home_assistant", "registered": True, "connected": True}
    ]
    assert overview["homes"][0]["home_id"] == home.id


@pytest.mark.asyncio
async def test_overview_unknown_home_propagates_error(
    service: DevtoolsConnectivityService,
) -> None:
    with pytest.raises(ServiceError):
        await service.get_overview("no-such-home")


# --- No fabricated telemetry ---------------------------------------------------------


@pytest.mark.asyncio
async def test_no_fabricated_telemetry_fields(
    service: DevtoolsConnectivityService, connectivity: ConnectivityService
) -> None:
    await connectivity.connect("home_assistant")

    rows = await service.get_connector_status()

    for row in rows:
        assert set(row) == {"connector_type", "registered", "connected"}
        for forbidden in ("latency", "uptime", "reconnect", "error_count", "last_seen"):
            assert forbidden not in row


@pytest.mark.asyncio
async def test_device_health_has_no_extra_fabricated_fields(
    service: DevtoolsConnectivityService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")

    rows = await service.get_device_health(home.id)

    assert set(rows[0]) == {
        "home_id",
        "room_count",
        "zone_count",
        "device_count",
        "paired_device_count",
        "offline_device_count",
        "unreachable_device_count",
    }


# --- Cross-cutting source guards ------------------------------------------------------


def _code_without_docstrings(module) -> str:
    """The module's source with every module/class/function docstring
    stripped, via a real AST transform -- this module's own docstrings
    are unusually explicit about exactly what they don't do (mentioning
    "EventBus", "credential", "metadata_json", "database" in
    explanatory prose), so a naive whole-source substring check would
    self-collide with its own documentation. What remains is real
    code: imports, attribute access, calls, literals."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            node.body.pop(0)
    return ast.unparse(tree)


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import devtools_connectivity_service as module

    import_lines = [
        line
        for line in inspect.getsource(module).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined


def test_service_has_no_eventbus_reference() -> None:
    from jarvis.services import devtools_connectivity_service as module

    code = _code_without_docstrings(module)
    assert "EventBus" not in code
    assert "event_bus" not in code


def test_service_does_not_touch_credential_store() -> None:
    from jarvis.services import devtools_connectivity_service as module

    code = _code_without_docstrings(module)
    assert "CredentialStore" not in code
    assert "credential" not in code.lower()


def test_service_does_not_read_device_metadata_json() -> None:
    from jarvis.services import devtools_connectivity_service as module

    code = _code_without_docstrings(module)
    assert "metadata_json" not in code


def test_service_has_no_database_dependency() -> None:
    from jarvis.services import devtools_connectivity_service as module

    code = _code_without_docstrings(module)
    assert "IDatabase" not in code
    assert "database" not in code.lower()


def test_service_never_calls_send_command() -> None:
    from jarvis.services import devtools_connectivity_service as module

    code = _code_without_docstrings(module)
    assert "send_command" not in code
