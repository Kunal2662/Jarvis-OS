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
from jarvis.services.smart_lighting_service import (
    SMART_LIGHTING_PRINCIPAL,
    SmartLightingService,
)
from jarvis.services.smart_lock_service import SMART_LOCK_PRINCIPAL, SmartLockService
from jarvis.services.thermostat_service import THERMOSTAT_PRINCIPAL, ThermostatService
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
def smart_lighting(
    db,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
) -> SmartLightingService:
    return SmartLightingService(
        database=db, smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def thermostats(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> ThermostatService:
    return ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


@pytest.fixture
def service(
    sensors: SensorService,
    smart_lock: SmartLockService,
    smart_lighting: SmartLightingService,
    thermostats: ThermostatService,
    smart_home: SmartHomeService,
    permissions: PermissionModel,
) -> SecurityService:
    return SecurityService(
        sensors=sensors,
        smart_lock=smart_lock,
        smart_lighting=smart_lighting,
        thermostats=thermostats,
        smart_home=smart_home,
        permissions=permissions,
    )


async def _grant_smart_lock(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_smart_lighting(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_LIGHTING_PRINCIPAL, SMART_HOME_SCOPE)


async def _grant_thermostats(permissions: PermissionModel) -> None:
    await permissions.grant(THERMOSTAT_PRINCIPAL, SMART_HOME_SCOPE)


async def _register_light(smart_home: SmartHomeService, home_id: str, *, external_id: str):
    return await smart_home.register_discovered_device(
        home_id,
        "Living Room Light",
        device_type="light",
        external_id=external_id,
        metadata={"connector_type": "home_assistant"},
    )


async def _register_thermostat(smart_home: SmartHomeService, home_id: str, *, external_id: str):
    return await smart_home.register_discovered_device(
        home_id,
        "Hallway Thermostat",
        device_type="thermostat",
        external_id=external_id,
        metadata={"connector_type": "home_assistant"},
    )


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


# =====================================================================
# Manual/On-Demand Action Slice (Task Group M) --
# docs/M12_SECURITY_ACTION_SLICE_LOGIC_CONTRACT.md
# =====================================================================


# --- Permission / home validation ---------------------------------------------------


@pytest.mark.asyncio
async def test_trigger_panic_mode_denied_without_core_security_grant(
    service: SecurityService, smart_home: SmartHomeService
) -> None:
    home = await _home(smart_home)
    with pytest.raises(SecurityPermissionError, match="permission"):
        await service.trigger_panic_mode(home.id)


@pytest.mark.asyncio
async def test_trigger_vacation_mode_denied_without_core_security_grant(
    service: SecurityService, smart_home: SmartHomeService
) -> None:
    home = await _home(smart_home)
    with pytest.raises(SecurityPermissionError, match="permission"):
        await service.trigger_vacation_mode(home.id)


@pytest.mark.asyncio
async def test_trigger_panic_mode_nonexistent_home_raises(
    service: SecurityService, permissions: PermissionModel
) -> None:
    """Unknown/inaccessible home_id -- this codebase has no separate
    per-home access-control layer beyond the session-wide Bearer
    token, so 'inaccessible' and 'nonexistent' are the same code path
    (Action Slice Logic Contract §4)."""
    await _grant_security(permissions)
    with pytest.raises(ServiceError, match="does not exist"):
        await service.trigger_panic_mode("no-such-home")


@pytest.mark.asyncio
async def test_trigger_vacation_mode_nonexistent_home_raises(
    service: SecurityService, permissions: PermissionModel
) -> None:
    await _grant_security(permissions)
    with pytest.raises(ServiceError, match="does not exist"):
        await service.trigger_vacation_mode("no-such-home")


@pytest.mark.asyncio
async def test_panic_mode_empty_home_is_no_targets(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant_security(permissions)
    home = await _home(smart_home)

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "NO_TARGETS"
    assert result["requested_count"] == 0
    assert result["locks"] == []
    assert result["lights"] == []
    assert result["thermostats"] == []


@pytest.mark.asyncio
async def test_vacation_mode_empty_home_is_no_targets(
    service: SecurityService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant_security(permissions)
    home = await _home(smart_home)

    result = await service.trigger_vacation_mode(home.id)

    assert result["status"] == "NO_TARGETS"


# --- Panic Mode -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_panic_mode_locks_and_lights_all_succeed(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "SUCCESS"
    assert result["mode"] == "panic"
    assert result["requested_count"] == 2
    assert result["succeeded_count"] == 2
    assert result["failed_count"] == 0
    assert result["thermostats"] == []
    assert ("lock.front_door", "lock", {}) in fake_connector.sent_commands
    assert ("light.living_room", "turn_on", {}) in fake_connector.sent_commands


@pytest.mark.asyncio
async def test_panic_mode_never_turns_off_or_unlocks(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="on", attributes={}
    )

    await service.trigger_panic_mode(home.id)

    commands_sent = {c[1] for c in fake_connector.sent_commands}
    assert "unlock" not in commands_sent
    assert "turn_off" not in commands_sent


@pytest.mark.asyncio
async def test_panic_mode_deterministic_order_locks_before_lights(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    home = await _home(smart_home)
    await _register_light(smart_home, home.id, external_id="light.living_room")
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    await service.trigger_panic_mode(home.id)

    order = [c[0] for c in fake_connector.sent_commands]
    assert order.index("lock.front_door") < order.index("light.living_room")


@pytest.mark.asyncio
async def test_panic_mode_partial_failure_when_lighting_not_granted(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Nested permission failure (core:smart_lighting not granted)
    surfaces as a per-device failure, never a top-level exception --
    the lock still succeeds (Action Slice Logic Contract §7)."""
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["locks"][0]["success"] is True
    assert result["lights"][0]["success"] is False
    assert "permission" in result["lights"][0]["detail"].lower()


@pytest.mark.asyncio
async def test_panic_mode_total_failure_when_nothing_granted(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "FAILED"
    assert result["succeeded_count"] == 0
    assert result["failed_count"] == 1


@pytest.mark.asyncio
async def test_panic_mode_unavailable_lock_not_attempted(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """A device whose Device.status is offline/unreachable is recorded
    unavailable without a wire attempt -- even without the underlying
    grant, proving it was never reached (Action Slice Logic Contract
    §4)."""
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    home = await _home(smart_home)
    lock = await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await smart_home.report_device_state(lock.id, status="offline")

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "FAILED"
    assert result["unavailable_count"] == 1
    assert result["succeeded_count"] == 0
    assert result["locks"][0]["detail"] == "device unavailable"
    assert fake_connector.sent_commands == []


@pytest.mark.asyncio
async def test_panic_mode_multiple_locks_and_lights(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    home = await _home(smart_home)
    for i in range(2):
        await _register_lock(smart_home, home.id, external_id=f"lock.door_{i}")
        fake_connector.states[f"lock.door_{i}"] = DeviceState(
            external_id=f"lock.door_{i}", status="unlocked", attributes={}
        )
    for i in range(2):
        await _register_light(smart_home, home.id, external_id=f"light.room_{i}")
        fake_connector.states[f"light.room_{i}"] = DeviceState(
            external_id=f"light.room_{i}", status="off", attributes={}
        )

    result = await service.trigger_panic_mode(home.id)

    assert result["status"] == "SUCCESS"
    assert result["requested_count"] == 4
    assert result["succeeded_count"] == 4
    assert len(result["locks"]) == 2
    assert len(result["lights"]) == 2


# --- Vacation Mode ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_vacation_mode_locks_lights_off_and_eco_thermostat(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="on", attributes={}
    )
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway",
        status="heat",
        attributes={"hvac_modes": ["heat", "cool", "eco", "off"]},
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["status"] == "SUCCESS"
    assert result["mode"] == "vacation"
    assert ("lock.front_door", "lock", {}) in fake_connector.sent_commands
    assert ("light.living_room", "turn_off", {}) in fake_connector.sent_commands
    assert (
        "climate.hallway",
        "set_hvac_mode",
        {"hvac_mode": "eco"},
    ) in fake_connector.sent_commands
    assert result["thermostats"][0]["success"] is True
    assert result["thermostats"][0]["skipped"] is False


@pytest.mark.asyncio
async def test_vacation_mode_never_turns_lights_on_or_unlocks(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="off", attributes={}
    )

    await service.trigger_vacation_mode(home.id)

    commands_sent = {c[1] for c in fake_connector.sent_commands}
    assert "unlock" not in commands_sent
    assert "turn_on" not in commands_sent


@pytest.mark.asyncio
async def test_vacation_mode_thermostat_without_eco_is_skipped(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway",
        status="heat",
        attributes={"hvac_modes": ["heat", "cool", "off"]},
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["thermostats"][0]["skipped"] is True
    assert result["thermostats"][0]["skip_reason"] == (
        "device does not report an eco-adjacent hvac_mode"
    )
    assert result["skipped_count"] == 1
    assert not any(c[0] == "climate.hallway" for c in fake_connector.sent_commands)


@pytest.mark.asyncio
async def test_vacation_mode_mixed_case_eco_token_matches(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway", status="heat", attributes={"hvac_modes": ["Heat", "ECO"]}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["thermostats"][0]["skipped"] is False
    assert result["thermostats"][0]["success"] is True


@pytest.mark.asyncio
async def test_vacation_mode_thermostat_unavailable_not_attempted(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway", status="unavailable", attributes={}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["thermostats"][0]["success"] is None
    assert result["thermostats"][0]["skipped"] is False
    assert result["unavailable_count"] == 1
    assert not any(c[0] == "climate.hallway" for c in fake_connector.sent_commands)


@pytest.mark.asyncio
async def test_vacation_mode_no_eco_capability_reported_never_falls_back_to_temperature(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No hvac_modes reported at all -- must skip, never invent a
    temperature-based fallback (Action Slice Logic Contract §5)."""
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway", status="heat", attributes={}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["thermostats"][0]["skipped"] is True
    assert not any(
        c[0] == "climate.hallway" and c[1] == "set_temperature"
        for c in fake_connector.sent_commands
    )


@pytest.mark.asyncio
async def test_vacation_mode_partial_failure(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="on", attributes={}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["status"] == "PARTIAL_SUCCESS"
    assert result["locks"][0]["success"] is True
    assert result["lights"][0]["success"] is False


@pytest.mark.asyncio
async def test_vacation_mode_total_failure(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["status"] == "FAILED"
    assert result["succeeded_count"] == 0


@pytest.mark.asyncio
async def test_deterministic_order_locks_lights_thermostats(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_smart_lighting(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_thermostat(smart_home, home.id, external_id="climate.hallway")
    await _register_light(smart_home, home.id, external_id="light.living_room")
    await _register_lock(smart_home, home.id, external_id="lock.front_door")
    fake_connector.states["climate.hallway"] = DeviceState(
        external_id="climate.hallway", status="heat", attributes={"hvac_modes": ["eco"]}
    )
    fake_connector.states["light.living_room"] = DeviceState(
        external_id="light.living_room", status="on", attributes={}
    )
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    await service.trigger_vacation_mode(home.id)

    order = [c[0] for c in fake_connector.sent_commands]
    assert order.index("lock.front_door") < order.index("light.living_room")
    assert order.index("light.living_room") < order.index("climate.hallway")


@pytest.mark.asyncio
async def test_exact_counts_and_status_across_mixed_outcomes(
    service: SecurityService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Comprehensive count check: 2 locks (1 succeeds, 1 fails -- no
    recorded connector), 1 light (unavailable), 1 thermostat (no eco,
    skipped)."""
    await connectivity.connect("home_assistant")
    await _grant_security(permissions)
    await _grant_smart_lock(permissions)
    await _grant_thermostats(permissions)
    home = await _home(smart_home)
    await _register_lock(smart_home, home.id, external_id="lock.good")
    fake_connector.states["lock.good"] = DeviceState(
        external_id="lock.good", status="unlocked", attributes={}
    )
    # A lock with no connector_type recorded at all -- lock() raises
    # "no recorded connector", caught as an ordinary per-device failure.
    await smart_home.register_discovered_device(
        home.id, "Orphan Lock", device_type="lock", external_id="lock.orphan"
    )
    light = await _register_light(smart_home, home.id, external_id="light.unavailable")
    await smart_home.report_device_state(light.id, status="offline")
    await _register_thermostat(smart_home, home.id, external_id="climate.no_eco")
    fake_connector.states["climate.no_eco"] = DeviceState(
        external_id="climate.no_eco", status="heat", attributes={"hvac_modes": ["heat"]}
    )

    result = await service.trigger_vacation_mode(home.id)

    assert result["requested_count"] == 4
    assert result["attempted_count"] == 2
    assert result["succeeded_count"] == 1
    assert result["failed_count"] == 1
    assert result["unavailable_count"] == 1
    assert result["skipped_count"] == 1
    assert result["status"] == "PARTIAL_SUCCESS"


# --- Cross-cutting source guards (Action Slice Logic Contract §8/§12) ---------------


def _code_without_docstrings(module) -> str:
    """The module's source with every module/class/function docstring
    stripped, via a real AST transform -- not a source guard's own
    problem to fabricate false positives out of prose that
    *describes* what the code deliberately does not do (this module's
    docstrings are unusually explicit about exactly that, on purpose).
    What remains is real code: imports, attribute access, calls,
    literals -- the only thing a "this symbol/term must not appear"
    guard should ever be checking."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body.pop(0)
    return ast.unparse(tree)


def test_action_slice_has_no_eventbus_reference() -> None:
    from jarvis.services import security_service as security_module

    code = _code_without_docstrings(security_module)
    assert "EventBus" not in code
    assert "event_bus" not in code


def test_action_slice_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import security_service as security_module

    import_lines = [
        line
        for line in inspect.getsource(security_module).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
    assert "gmqtt" not in joined
    assert "connectors" not in joined.lower()


def test_action_slice_has_no_deferred_functionality() -> None:
    """Scheduling, randomization, notifications, sirens, cameras,
    presets, temperature fallback -- none of it exists anywhere in the
    real implementation (Action Slice Logic Contract §12). Checked
    against code with docstrings stripped -- this module's own
    docstrings *name* several of these deferred terms explicitly, as
    prose explaining they are out of scope, which is the documentation
    this codebase wants, not a guard-test false positive."""
    from jarvis.services import security_service as security_module

    code = _code_without_docstrings(security_module).lower()
    for deferred_term in (
        "schedule",
        "randomiz",
        "geofenc",
        "notification",
        "siren",
        "alarm_control_panel",
        "camera",
        "vision",
        "preset_mode",
        "away_mode",
        "sms",
        "email",
        "push_notification",
    ):
        assert deferred_term not in code


def test_confirm_required_tools_includes_both_action_tools() -> None:
    from jarvis.core.config.settings import AgentSettings

    confirm_required = AgentSettings().confirm_required_tools
    assert "trigger_panic_mode" in confirm_required
    assert "trigger_vacation_mode" in confirm_required
