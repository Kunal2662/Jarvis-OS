"""SecurityService tests -- Milestone 12 Security & Safety (Read-Only
Alert/Status Slice).

Real (temp-file) SQLite ``SmartHomeService``, real ``SensorService``/
``SmartLockService``, and a real ``PermissionModel`` throughout --
matching ``test_m12_sensor_service.py``/``test_m12_smart_lock_service.
py``'s own pattern; only the connector itself is faked
(``FakeDeviceConnector``). ``SecurityService`` is never given a
mock/fake of its two dependencies -- it is tested against the real,
already-tested services it aggregates.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.security_service import (
    SECURITY_PRINCIPAL,
    SMART_HOME_SCOPE,
    SecurityPermissionError,
    SecurityService,
)
from jarvis.services.sensor_service import SENSOR_PRINCIPAL
from jarvis.services.sensor_service import SensorPermissionError as SensorPermError
from jarvis.services.sensor_service import SensorService
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
def permissions(tmp_path: Path, bus: EventBus) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


@pytest.fixture
def sensors(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SensorService:
    return SensorService(smart_home=smart_home, connectivity=connectivity, permissions=permissions)


@pytest.fixture
def smart_lock(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartLockService:
    return SmartLockService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def service(
    sensors: SensorService, smart_lock: SmartLockService, permissions: PermissionModel
) -> SecurityService:
    return SecurityService(sensors=sensors, smart_lock=smart_lock, permissions=permissions)


async def _grant_security(permissions: PermissionModel) -> None:
    await permissions.grant(SECURITY_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_sensors(permissions: PermissionModel) -> None:
    await permissions.grant(SENSOR_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_all(permissions: PermissionModel) -> None:
    await _grant_security(permissions)
    await _grant_sensors(permissions)


async def _home(smart_home: SmartHomeService):
    return await smart_home.create_home("Primary Residence")


async def _register_hazard_sensor(
    smart_home: SmartHomeService,
    home_id: str,
    *,
    device_class: str,
    external_id: str,
    room_id: str | None = None,
):
    return await smart_home.register_discovered_device(
        home_id,
        f"{device_class.title()} Sensor",
        device_type="sensor",
        room_id=room_id,
        external_id=external_id,
        metadata={
            "connector_type": "home_assistant",
            "domain": "binary_sensor",
            "device_class": device_class,
        },
    )


async def _register_status_sensor(
    smart_home: SmartHomeService, home_id: str, *, device_class: str, external_id: str
):
    return await smart_home.register_discovered_device(
        home_id,
        f"{device_class.title()} Sensor",
        device_type="sensor",
        external_id=external_id,
        metadata={
            "connector_type": "home_assistant",
            "domain": "binary_sensor",
            "device_class": device_class,
        },
    )


async def _register_lock(smart_home: SmartHomeService, home_id: str, *, external_id: str):
    return await smart_home.register_discovered_device(
        home_id,
        "Front Door",
        device_type="lock",
        external_id=external_id,
        metadata={"connector_type": "home_assistant"},
    )


# --- Permission enforcement ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_security_status_denied_without_core_security_grant(
    service: SecurityService,
) -> None:
    with pytest.raises(SecurityPermissionError, match="permission"):
        await service.get_security_status()


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SECURITY_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


def test_security_permission_error_is_a_service_error() -> None:
    assert issubclass(SecurityPermissionError, ServiceError)


@pytest.mark.asyncio
async def test_core_security_and_core_sensors_are_independently_grantable(
    permissions: PermissionModel,
) -> None:
    """Granting one principal must not implicitly grant the other --
    Logic Contract §3/§14."""
    await _grant_security(permissions)
    assert permissions.is_granted(SECURITY_PRINCIPAL, SMART_HOME_SCOPE) is True
    assert permissions.is_granted(SENSOR_PRINCIPAL, SMART_HOME_SCOPE) is False


@pytest.mark.asyncio
async def test_sensor_permission_error_propagates_not_swallowed(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """core:security granted, core:sensors NOT granted -> the nested
    SensorPermissionError propagates as-is; it is never caught and
    turned into a silently-empty/'all clear' result (Logic Contract
    §3)."""
    await _grant_security(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )

    with pytest.raises(SensorPermError, match="permission"):
        await service.get_security_status()


# --- Normal / empty states --------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_home_reports_unknown_and_empty_lists(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant_all(permissions)
    await _home(smart_home)

    status = await service.get_security_status()

    assert status["overall_status"] == "UNKNOWN"
    assert status["active_alerts"] == []
    assert status["hazard_sensors"] == []
    assert status["status_sensors"] == []
    assert status["locks"] == []
    assert status["unavailable_count"] == 0


@pytest.mark.asyncio
async def test_all_hazard_sensors_clear_is_normal(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="off", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "NORMAL"
    assert status["active_alerts"] == []
    assert status["hazard_sensors"][0]["signal"] == "CLEAR"


@pytest.mark.asyncio
async def test_no_hazard_sensors_but_status_sensors_exist_is_unknown(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_status_sensor(
        smart_home, home.id, device_class="door", external_id="binary_sensor.door_1"
    )
    fake_connector.states["binary_sensor.door_1"] = DeviceState(
        external_id="binary_sensor.door_1", status="on", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "UNKNOWN"
    assert len(status["status_sensors"]) == 1


# --- Hazard alerts (smoke/gas/moisture only) ---------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("device_class", ["smoke", "gas", "moisture"])
async def test_hazard_detected_is_critical_and_in_active_alerts(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    device_class: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    external_id = f"binary_sensor.{device_class}_1"
    await _register_hazard_sensor(
        smart_home, home.id, device_class=device_class, external_id=external_id
    )
    fake_connector.states[external_id] = DeviceState(
        external_id=external_id, status="on", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "CRITICAL"
    assert len(status["active_alerts"]) == 1
    assert status["active_alerts"][0]["device_class"] == device_class


@pytest.mark.asyncio
async def test_multiple_simultaneous_alerts_all_reported(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    for device_class in ("smoke", "gas"):
        external_id = f"binary_sensor.{device_class}_1"
        await _register_hazard_sensor(
            smart_home, home.id, device_class=device_class, external_id=external_id
        )
        fake_connector.states[external_id] = DeviceState(
            external_id=external_id, status="on", attributes={}
        )

    status = await service.get_security_status()

    assert status["overall_status"] == "CRITICAL"
    assert len(status["active_alerts"]) == 2
    assert {a["device_class"] for a in status["active_alerts"]} == {"smoke", "gas"}


# --- Status-only sensors never become alerts (the core non-inference invariant) ----


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "device_class,raw_status",
    [
        ("door", "on"),
        ("window", "on"),
        ("garage_door", "on"),
        ("motion", "on"),
        ("presence", "on"),
        ("occupancy", "on"),
        ("vibration", "on"),
    ],
)
async def test_status_only_classes_never_become_alerts_or_move_overall_status(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    device_class: str,
    raw_status: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    external_id = f"binary_sensor.{device_class}_1"
    await _register_status_sensor(
        smart_home, home.id, device_class=device_class, external_id=external_id
    )
    fake_connector.states[external_id] = DeviceState(
        external_id=external_id, status=raw_status, attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "UNKNOWN"  # no hazard sensors paired at all
    assert status["active_alerts"] == []
    assert len(status["status_sensors"]) == 1
    assert status["status_sensors"][0]["device_class"] == device_class


@pytest.mark.asyncio
async def test_open_door_alongside_clear_hazard_sensor_stays_normal(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """The direct test of 'door open must not become intrusion': a
    hazard sensor confirms NORMAL while a door is open at the same
    time."""
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="off", attributes={}
    )
    await _register_status_sensor(
        smart_home, home.id, device_class="door", external_id="binary_sensor.door_1"
    )
    fake_connector.states["binary_sensor.door_1"] = DeviceState(
        external_id="binary_sensor.door_1", status="on", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "NORMAL"
    assert status["active_alerts"] == []


# --- Lock state -- informational only ----------------------------------------------


@pytest.mark.asyncio
async def test_lock_state_reported_but_never_affects_overall_status(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "UNKNOWN"  # no hazard sensors at all
    assert len(status["locks"]) == 1
    assert status["locks"][0]["locked"] is False


@pytest.mark.asyncio
async def test_unavailable_lock_reports_unknown_locked_and_counts_unavailable(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """No connector connected -- ConnectivityError -> available=False,
    locked=None, per SmartLockService.get_lock_state's own fallback."""
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")

    status = await service.get_security_status()

    assert status["locks"][0]["available"] is False
    assert status["locks"][0]["locked"] is None
    assert status["unavailable_count"] == 1


# --- Unavailable hazard sensors -- never NORMAL -------------------------------------


@pytest.mark.asyncio
async def test_unavailable_hazard_sensor_is_warning_not_normal(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    """No connector connected at all -- the hazard sensor's read fails
    (ConnectivityError, absorbed by SensorService into available=False)
    -- must be WARNING, never silently NORMAL."""
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "WARNING"
    assert status["hazard_sensors"][0]["signal"] == "UNKNOWN"
    assert status["unavailable_count"] == 1


@pytest.mark.parametrize("offline_status", ["offline", "unavailable"])
@pytest.mark.asyncio
async def test_connector_reported_offline_hazard_sensor_is_warning(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
    offline_status: str,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="gas", external_id="binary_sensor.gas_1"
    )
    fake_connector.states["binary_sensor.gas_1"] = DeviceState(
        external_id="binary_sensor.gas_1", status=offline_status, attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "WARNING"
    assert status["hazard_sensors"][0]["signal"] == "UNKNOWN"


# --- Deterministic precedence -------------------------------------------------------


@pytest.mark.asyncio
async def test_critical_wins_over_warning_when_both_present(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    # One ACTIVE (smoke), one UNKNOWN (gas, never given a fake state).
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="on", attributes={}
    )
    await _register_hazard_sensor(
        smart_home, home.id, device_class="gas", external_id="binary_sensor.gas_1"
    )
    fake_connector.states["binary_sensor.gas_1"] = DeviceState(
        external_id="binary_sensor.gas_1", status="unavailable", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "CRITICAL"


@pytest.mark.asyncio
async def test_warning_wins_over_normal_when_one_hazard_sensor_unavailable(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    # One CLEAR (smoke), one UNKNOWN (gas).
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="off", attributes={}
    )
    await _register_hazard_sensor(
        smart_home, home.id, device_class="gas", external_id="binary_sensor.gas_1"
    )
    fake_connector.states["binary_sensor.gas_1"] = DeviceState(
        external_id="binary_sensor.gas_1", status="unavailable", attributes={}
    )

    status = await service.get_security_status()

    assert status["overall_status"] == "WARNING"


# --- Filtering -----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_room_filter_scopes_the_aggregate(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    room_a = await smart_home.create_room(home.id, "Kitchen")
    room_b = await smart_home.create_room(home.id, "Garage")

    await _register_hazard_sensor(
        smart_home,
        home.id,
        device_class="smoke",
        external_id="binary_sensor.smoke_kitchen",
        room_id=room_a.id,
    )
    fake_connector.states["binary_sensor.smoke_kitchen"] = DeviceState(
        external_id="binary_sensor.smoke_kitchen", status="off", attributes={}
    )
    await _register_hazard_sensor(
        smart_home,
        home.id,
        device_class="gas",
        external_id="binary_sensor.gas_garage",
        room_id=room_b.id,
    )
    fake_connector.states["binary_sensor.gas_garage"] = DeviceState(
        external_id="binary_sensor.gas_garage", status="on", attributes={}
    )

    kitchen_status = await service.get_security_status(home_id=home.id, room_id=room_a.id)
    garage_status = await service.get_security_status(home_id=home.id, room_id=room_b.id)

    assert kitchen_status["overall_status"] == "NORMAL"
    assert garage_status["overall_status"] == "CRITICAL"


# --- list_active_alerts (tool-facing thin slice) ------------------------------------


@pytest.mark.asyncio
async def test_list_active_alerts_matches_get_security_status_active_alerts(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_all(permissions)
    home = await _home(smart_home)
    await _register_hazard_sensor(
        smart_home, home.id, device_class="smoke", external_id="binary_sensor.smoke_1"
    )
    fake_connector.states["binary_sensor.smoke_1"] = DeviceState(
        external_id="binary_sensor.smoke_1", status="on", attributes={}
    )

    alerts = await service.list_active_alerts()
    full = await service.get_security_status()

    assert alerts == full["active_alerts"]


@pytest.mark.asyncio
async def test_list_active_alerts_denied_without_grant(service: SecurityService) -> None:
    with pytest.raises(SecurityPermissionError):
        await service.list_active_alerts()


# --- Cross-cutting: no duplicated normalization logic --------------------------------


def test_security_service_does_not_duplicate_sensor_or_lock_normalization() -> None:
    import inspect

    from jarvis.services import security_service as security_module

    source = inspect.getsource(security_module)
    # These are SensorService's/SmartLockService's own private helpers --
    # SecurityService must call the public methods, never reimplement
    # the normalization itself.
    for leaked_term in ("_parse_binary", "_infer_locked", "_binary_state_label"):
        assert leaked_term not in source
