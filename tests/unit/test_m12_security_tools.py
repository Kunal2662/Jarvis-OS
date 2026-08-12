"""Security & Safety agent tool tests -- Milestone 12 Security & Safety
(Read-Only Alert/Status Slice).

Real ``SecurityService`` over real ``SensorService``/``SmartLockService``,
real (temp-file) SQLite, a real ``PermissionModel`` and a
``FakeDeviceConnector``, matching ``test_m12_sensor_tools.py``'s own
fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("langchain_core")

from jarvis.agents.tools.security_tools import build_security_tools
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.security_service import SECURITY_PRINCIPAL, SMART_HOME_SCOPE, SecurityService
from jarvis.services.sensor_service import SENSOR_PRINCIPAL, SensorService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lock_service import SmartLockService
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
def fake_connector() -> FakeDeviceConnector:
    return FakeDeviceConnector()


@pytest.fixture
def smart_home(db) -> SmartHomeService:
    return SmartHomeService(database=db, event_bus=EventBus())


@pytest.fixture
def connectivity(
    fake_connector: FakeDeviceConnector, smart_home: SmartHomeService
) -> ConnectivityService:
    registry = ConnectorFactoryRegistry()
    registry.register("home_assistant", lambda config: fake_connector)
    return ConnectivityService(registry=registry, smart_home=smart_home)


@pytest.fixture
def permissions(tmp_path: Path) -> PermissionModel:
    return PermissionModel(EventBus(), store_path=tmp_path / "permissions.json")


@pytest.fixture
def sensors(smart_home, connectivity, permissions) -> SensorService:
    return SensorService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


@pytest.fixture
def smart_lock(smart_home, connectivity, permissions) -> SmartLockService:
    return SmartLockService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def service(sensors, smart_lock, permissions) -> SecurityService:
    return SecurityService(sensors=sensors, smart_lock=smart_lock, permissions=permissions)


@pytest.fixture
def tools(service: SecurityService):
    return {t.name: t for t in build_security_tools(service)}


async def _grant_security(permissions: PermissionModel) -> None:
    await permissions.grant(SECURITY_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_sensors(permissions: PermissionModel) -> None:
    await permissions.grant(SENSOR_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_all(permissions: PermissionModel) -> None:
    await _grant_security(permissions)
    await _grant_sensors(permissions)


async def _register_hazard_sensor(smart_home: SmartHomeService, *, device_class: str = "smoke"):
    home = await smart_home.create_home("Primary Residence")
    return await smart_home.register_discovered_device(
        home.id,
        f"{device_class.title()} Sensor",
        device_type="sensor",
        external_id=f"binary_sensor.{device_class}_1",
        metadata={
            "connector_type": "home_assistant",
            "domain": "binary_sensor",
            "device_class": device_class,
        },
    )


# --- Registry registration -----------------------------------------------------


def test_registry_omits_security_tools_when_not_wired() -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    assert build_tool_registry() == []


@pytest.mark.asyncio
async def test_registry_includes_security_tools_when_service_provided(
    service: SecurityService,
) -> None:
    from jarvis.agents.tools.registry import build_tool_registry

    tools = build_tool_registry(security=service)
    names = {t.name for t in tools}
    assert {"get_security_status", "list_active_security_alerts"} <= names


# --- Permission enforcement -------------------------------------------------------


@pytest.mark.asyncio
async def test_get_security_status_tool_denied_without_grant(tools) -> None:
    result = await tools["get_security_status"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_list_active_security_alerts_tool_denied_without_grant(tools) -> None:
    result = await tools["list_active_security_alerts"].ainvoke({})
    assert "Couldn't" in result
    assert "permission" in result.lower()


@pytest.mark.asyncio
async def test_get_security_status_tool_denied_when_only_security_granted(
    tools, permissions: PermissionModel, smart_home: SmartHomeService
) -> None:
    """core:security alone is not enough once a hazard sensor exists --
    the nested core:sensors check still applies (Logic Contract §3)."""
    await _grant_security(permissions)
    await _register_hazard_sensor(smart_home)

    result = await tools["get_security_status"].ainvoke({})

    assert "Couldn't" in result
    assert "permission" in result.lower()


# --- Basic tool behavior, once granted --------------------------------------------


@pytest.mark.asyncio
async def test_get_security_status_tool_reports_unknown_for_empty_home(
    tools, permissions: PermissionModel, smart_home: SmartHomeService
) -> None:
    await _grant_all(permissions)
    await smart_home.create_home("Primary Residence")

    result = await tools["get_security_status"].ainvoke({})

    assert '"overall_status": "UNKNOWN"' in result


@pytest.mark.asyncio
async def test_get_security_status_tool_reports_critical_on_active_hazard(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    await _register_hazard_sensor(smart_home, device_class="smoke")
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="on", attributes={}
    )

    result = await tools["get_security_status"].ainvoke({})

    assert '"overall_status": "CRITICAL"' in result


@pytest.mark.asyncio
async def test_list_active_security_alerts_tool_reports_no_alerts(
    tools, permissions: PermissionModel, smart_home: SmartHomeService
) -> None:
    await _grant_all(permissions)
    await smart_home.create_home("Primary Residence")

    result = await tools["list_active_security_alerts"].ainvoke({})

    assert result == "No active alerts."


@pytest.mark.asyncio
async def test_list_active_security_alerts_tool_returns_terse_alert_only_shape(
    tools,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    await _register_hazard_sensor(smart_home, device_class="gas")
    fake_connector.states["binary_sensor.gas_1"] = DeviceState(
        external_id="binary_sensor.gas_1", status="on", attributes={}
    )

    result = await tools["list_active_security_alerts"].ainvoke({})

    assert '"device_class": "gas"' in result
    assert "hazard_sensors" not in result  # terse -- alerts only, not the full aggregate.


@pytest.mark.asyncio
async def test_get_security_status_tool_reports_error_without_raising(tools) -> None:
    """A tool never raises out to the agent loop -- any failure is a
    string, matching every other M12 tool file's convention."""
    result = await tools["get_security_status"].ainvoke({})
    assert isinstance(result, str)


# --- No mutation tool ----------------------------------------------------------------


def test_no_mutation_tool_is_built(service: SecurityService) -> None:
    built = {t.name for t in build_security_tools(service)}
    assert built == {"get_security_status", "list_active_security_alerts"}
