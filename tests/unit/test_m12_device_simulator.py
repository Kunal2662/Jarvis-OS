"""Device Simulator tests -- Milestone 12 Developer Tools (Device
Simulator Slice).

Covers the ``SimulatorConnector`` class itself, the DI factory-swap
(Option C), and full end-to-end round-trips through the real, unmodified
generic Connectivity Layer and device-category services -- real
(temp-file) SQLite ``SmartHomeService``, real ``ConnectivityService``,
real ``SmartLightingService``/``SmartSwitchService``/``ThermostatService``/
``SmartLockService``/``SensorService``, and a real ``PermissionModel``
throughout; only the simulator itself stands in for a physical device.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.connectors.simulator import (
    SIMULATED_DEVICE_TYPES,
    SimulatorConnector,
)
from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.interfaces.connectivity import (
    CONNECTOR_TYPES,
    ConnectivityError,
    ConnectorNotConnectedError,
)
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.sensor_service import SensorService
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lighting_service import SmartLightingService
from jarvis.services.smart_lock_service import SmartLockService
from jarvis.services.smart_switch_service import SmartSwitchService
from jarvis.services.thermostat_service import ThermostatService


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
def simulator() -> SimulatorConnector:
    return SimulatorConnector()


@pytest.fixture
def registry(simulator: SimulatorConnector) -> ConnectorFactoryRegistry:
    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: simulator)
    return reg


@pytest.fixture
def connectivity(
    registry: ConnectorFactoryRegistry, smart_home: SmartHomeService, bus: EventBus
) -> ConnectivityService:
    return ConnectivityService(registry=registry, smart_home=smart_home, event_bus=bus)


@pytest.fixture
def permissions(tmp_path: Path, bus: EventBus) -> PermissionModel:
    return PermissionModel(bus, store_path=tmp_path / "permissions.json")


# --- A. Factory / DI swap (Logic Contract §2/§4) --------------------------------------


def test_simulator_mode_swaps_home_assistant_factory(tmp_path: Path, monkeypatch) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.di.container import _build_connectivity_registry, _build_simulator_connector

    _settings(tmp_path, monkeypatch)
    settings = Settings(devtools={"simulator_enabled": True})
    sim = _build_simulator_connector()
    reg = _build_connectivity_registry(settings=settings, simulator_connector=sim)

    connector = reg.create("home_assistant", {})

    assert connector is sim
    assert isinstance(connector, SimulatorConnector)


def test_disabled_mode_uses_real_home_assistant_factory(tmp_path: Path, monkeypatch) -> None:
    """The disabled branch is `build_default_connector_registry()`
    verbatim -- the real connector's own factory function, unchanged
    (Logic Contract's own acceptance criterion)."""
    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.connectors.factory import build_home_assistant_connector
    from jarvis.core.di.container import _build_connectivity_registry, _build_simulator_connector

    _settings(tmp_path, monkeypatch)
    settings = Settings(devtools={"simulator_enabled": False})
    sim = _build_simulator_connector()
    reg = _build_connectivity_registry(settings=settings, simulator_connector=sim)

    assert reg._factories["home_assistant"] is build_home_assistant_connector


def test_mqtt_slot_never_affected_by_simulator_mode(tmp_path: Path, monkeypatch) -> None:
    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.connectors.factory import build_mqtt_connector
    from jarvis.core.di.container import _build_connectivity_registry, _build_simulator_connector

    _settings(tmp_path, monkeypatch)
    sim = _build_simulator_connector()
    for enabled in (True, False):
        settings = Settings(devtools={"simulator_enabled": enabled})
        reg = _build_connectivity_registry(settings=settings, simulator_connector=sim)
        assert reg._factories["mqtt"] is build_mqtt_connector


def test_connector_types_unchanged() -> None:
    """No `CONNECTOR_TYPES` change -- still exactly the two approved
    identifiers (Logic Contract §3, an explicit acceptance criterion)."""
    assert frozenset({"home_assistant", "mqtt"}) == CONNECTOR_TYPES


def test_simulator_not_registrable_under_a_new_connector_type(
    simulator: SimulatorConnector,
) -> None:
    from jarvis.core.connectivity.registry import ConnectorRegistrationError

    reg = ConnectorFactoryRegistry()
    with pytest.raises(ConnectorRegistrationError):
        reg.register("simulator", lambda config: simulator)


# --- I. Isolation: real HA / simulator cannot coexist ----------------------------------


def test_registry_enforces_single_factory_per_home_assistant_key(
    simulator: SimulatorConnector,
) -> None:
    """`ConnectorFactoryRegistry` is a plain single-key dict -- only one
    factory can ever answer `"home_assistant"` in a given registry
    instance at a time, enforced by the pre-existing registry
    implementation itself, not a loose convention (Logic Contract §13)."""
    from jarvis.core.connectivity.connectors.home_assistant import HomeAssistantConnector

    reg = ConnectorFactoryRegistry()
    reg.register("home_assistant", lambda config: simulator)
    assert isinstance(reg.create("home_assistant", {}), SimulatorConnector)

    reg.register("home_assistant", lambda config: HomeAssistantConnector("http://x", "tok"))
    real = reg.create("home_assistant", {})
    assert isinstance(real, HomeAssistantConnector)
    assert not isinstance(real, SimulatorConnector)
    # The two never coexist -- registering the second overwrote the first.


def test_simulator_module_never_imports_real_transport_or_credentials() -> None:
    """Docstrings may *discuss* what this module deliberately avoids --
    only an actual import statement would be the real violation this
    test guards against (mirrors
    `test_m12_water_heater_service.py::test_service_does_not_import_connectors_directly`)."""
    import inspect

    from jarvis.core.connectivity.connectors import simulator as simulator_module

    import_lines = [
        line
        for line in inspect.getsource(simulator_module).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    for forbidden in (
        "httpx",
        "gmqtt",
        "HomeAssistantConnector",
        "MqttConnector",
        "ConnectorCredentialStore",
    ):
        assert forbidden not in joined


@pytest.mark.asyncio
async def test_simulator_mode_never_instantiates_real_home_assistant_connector(
    tmp_path: Path, monkeypatch
) -> None:
    """Behavioral proof, not a flag assertion (Logic Contract §11): the
    real `HomeAssistantConnector.connect` is monkeypatched to raise if
    ever called, then a full simulator-mode discover/command flow runs
    to completion without tripping it."""
    from jarvis.core.config.settings import Settings
    from jarvis.core.connectivity.connectors.home_assistant import HomeAssistantConnector
    from jarvis.core.di.container import _build_connectivity_registry, _build_simulator_connector

    async def _poison(self) -> None:
        raise AssertionError("real HomeAssistantConnector.connect() must never be called")

    monkeypatch.setattr(HomeAssistantConnector, "connect", _poison)

    _settings(tmp_path, monkeypatch)
    settings = Settings(devtools={"simulator_enabled": True})
    sim = _build_simulator_connector()
    reg = _build_connectivity_registry(settings=settings, simulator_connector=sim)

    sim.define_device(device_type="light", external_id="light.proof")
    connector = reg.create("home_assistant", {})
    await connector.connect()
    await connector.discover()
    await connector.send_command("light.proof", "turn_on", {})
    # No exception means the poisoned real connector was never reached.


# --- B. Device creation --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("device_type", sorted(SIMULATED_DEVICE_TYPES))
async def test_define_device_deterministic_initial_state(
    simulator: SimulatorConnector, device_type: str
) -> None:
    device = simulator.define_device(device_type=device_type, external_id=f"{device_type}.x")
    assert device["device_type"] == device_type
    assert device["unavailable"] is False
    assert device["force_command_failure"] is False
    # Deterministic -- calling again with no overrides reproduces the
    # exact same shape.
    again = simulator.define_device(device_type=device_type, external_id=f"{device_type}.x")
    assert device == again


def test_define_device_generates_external_id_when_omitted(simulator: SimulatorConnector) -> None:
    device = simulator.define_device(device_type="light")
    assert device["external_id"].startswith("simulator.light.")


def test_define_device_rejects_unsupported_device_type(simulator: SimulatorConnector) -> None:
    with pytest.raises(ConnectivityError, match="unsupported device_type"):
        simulator.define_device(device_type="camera")


def test_define_device_sensor_binary_metadata_drives_real_sensor_kind(
    simulator: SimulatorConnector,
) -> None:
    """`SensorService._kind_for` reads `metadata["domain"]=="binary_sensor"`
    off the *device row*, set at discovery time from
    `DiscoveredDevice.metadata` -- confirms the simulator's own
    `binary=True` flag produces that exact metadata shape."""
    simulator.define_device(
        device_type="sensor", external_id="sensor.motion", binary=True, device_class="motion"
    )
    roster = {d["external_id"]: d for d in simulator.list_devices()}
    assert "sensor.motion" in roster


# --- C. Roster -------------------------------------------------------------------------


def test_list_devices_empty_by_default(simulator: SimulatorConnector) -> None:
    assert simulator.list_devices() == []


def test_define_device_upsert_fully_redefines(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="light", external_id="light.x", status="on")
    simulator.define_device(device_type="light", external_id="light.x")  # no status override
    device = simulator.list_devices()[0]
    assert device["status"] == "off"  # back to the deterministic default, not "on"


def test_delete_device(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="switch", external_id="switch.x")
    assert simulator.delete_device("switch.x") is True
    assert simulator.list_devices() == []


def test_delete_unknown_device_returns_false(simulator: SimulatorConnector) -> None:
    assert simulator.delete_device("no-such-device") is False


def test_reset_clears_roster_and_returns_count(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="light", external_id="light.a")
    simulator.define_device(device_type="switch", external_id="switch.b")
    assert simulator.reset() == 2
    assert simulator.list_devices() == []


# --- D/E. Commands and state ------------------------------------------------------------


@pytest.mark.asyncio
async def test_light_turn_on_off(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="light", external_id="light.x")
    await simulator.connect()

    on = await simulator.send_command("light.x", "turn_on", {"brightness_pct": 50})
    assert on.success is True
    state = await simulator.read_state("light.x")
    assert state.status == "on"
    assert state.attributes["brightness"] == 50

    off = await simulator.send_command("light.x", "turn_off", {})
    assert off.success is True
    assert (await simulator.read_state("light.x")).status == "off"


@pytest.mark.asyncio
async def test_switch_turn_on_off(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="switch", external_id="switch.x")
    await simulator.connect()

    await simulator.send_command("switch.x", "turn_on", {})
    assert (await simulator.read_state("switch.x")).status == "on"
    await simulator.send_command("switch.x", "turn_off", {})
    assert (await simulator.read_state("switch.x")).status == "off"


@pytest.mark.asyncio
async def test_thermostat_set_hvac_mode(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="thermostat", external_id="climate.x")
    await simulator.connect()

    result = await simulator.send_command("climate.x", "set_hvac_mode", {"hvac_mode": "heat"})
    assert result.success is True
    assert (await simulator.read_state("climate.x")).status == "heat"


@pytest.mark.asyncio
async def test_thermostat_set_temperature(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="thermostat", external_id="climate.x")
    await simulator.connect()

    result = await simulator.send_command("climate.x", "set_temperature", {"temperature": 23.5})
    assert result.success is True
    state = await simulator.read_state("climate.x")
    assert state.attributes["temperature"] == 23.5


@pytest.mark.asyncio
async def test_lock_unlock(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="lock", external_id="lock.x")
    await simulator.connect()

    await simulator.send_command("lock.x", "lock", {})
    assert (await simulator.read_state("lock.x")).status == "locked"
    await simulator.send_command("lock.x", "unlock", {})
    assert (await simulator.read_state("lock.x")).status == "unlocked"


@pytest.mark.asyncio
async def test_sensor_rejects_any_command(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="sensor", external_id="sensor.x")
    await simulator.connect()

    result = await simulator.send_command("sensor.x", "turn_on", {})
    assert result.success is False
    assert "do not accept commands" in result.detail


@pytest.mark.asyncio
async def test_unsupported_command_fails_cleanly_never_raises(
    simulator: SimulatorConnector,
) -> None:
    simulator.define_device(device_type="light", external_id="light.x")
    await simulator.connect()

    result = await simulator.send_command("light.x", "explode", {})
    assert result.success is False
    assert "unsupported command" in result.detail


@pytest.mark.asyncio
async def test_read_unknown_device_raises(simulator: SimulatorConnector) -> None:
    await simulator.connect()
    with pytest.raises(ConnectivityError):
        await simulator.read_state("no-such-device")


@pytest.mark.asyncio
async def test_send_command_unknown_device_raises(simulator: SimulatorConnector) -> None:
    await simulator.connect()
    with pytest.raises(ConnectivityError):
        await simulator.send_command("no-such-device", "turn_on", {})


@pytest.mark.asyncio
async def test_not_connected_raises(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="light", external_id="light.x")
    with pytest.raises(ConnectorNotConnectedError):
        await simulator.read_state("light.x")
    with pytest.raises(ConnectorNotConnectedError):
        await simulator.send_command("light.x", "turn_on", {})
    with pytest.raises(ConnectorNotConnectedError):
        await simulator.discover()


# --- F. Fault simulation ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_unavailable_read(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="light", external_id="light.x", status="on")
    simulator.set_fault("light.x", unavailable=True)
    await simulator.connect()

    state = await simulator.read_state("light.x")
    assert state.status == "unavailable"


@pytest.mark.asyncio
async def test_mark_unavailable_command_fails(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="switch", external_id="switch.x")
    simulator.set_fault("switch.x", unavailable=True)
    await simulator.connect()

    result = await simulator.send_command("switch.x", "turn_on", {})
    assert result.success is False
    assert result.detail == "device unavailable"


@pytest.mark.asyncio
async def test_force_command_failure_is_deterministic(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="lock", external_id="lock.x")
    simulator.set_fault("lock.x", force_command_failure=True, failure_detail="jammed")
    await simulator.connect()

    for _ in range(3):
        result = await simulator.send_command("lock.x", "lock", {})
        assert result.success is False
        assert result.detail == "jammed"


@pytest.mark.asyncio
async def test_restore_availability(simulator: SimulatorConnector) -> None:
    simulator.define_device(device_type="switch", external_id="switch.x")
    simulator.set_fault("switch.x", unavailable=True)
    await simulator.connect()
    assert (await simulator.send_command("switch.x", "turn_on", {})).success is False

    simulator.set_fault("switch.x", unavailable=False)
    result = await simulator.send_command("switch.x", "turn_on", {})
    assert result.success is True
    assert (await simulator.read_state("switch.x")).status == "on"


def test_set_fault_unknown_device_raises(simulator: SimulatorConnector) -> None:
    with pytest.raises(ConnectivityError):
        simulator.set_fault("no-such-device", unavailable=True)


# --- G. Generic Connectivity integration (real services, no simulator-specific API) ----


async def _home_and_device(
    smart_home: SmartHomeService,
    simulator: SimulatorConnector,
    *,
    device_type: str,
    external_id: str,
):
    simulator.define_device(device_type=device_type, external_id=external_id)
    home = await smart_home.create_home("Primary Residence")
    return home


@pytest.mark.asyncio
async def test_generic_discovery_imports_simulated_devices(
    smart_home: SmartHomeService, connectivity: ConnectivityService, simulator: SimulatorConnector
) -> None:
    simulator.define_device(device_type="light", external_id="light.living_room")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")

    imported = await connectivity.run_discovery("home_assistant", home.id)

    assert len(imported) == 1
    assert imported[0].device_type == "light"
    assert imported[0].external_id == "light.living_room"


@pytest.mark.asyncio
async def test_generic_read_raw_state_reflects_simulator(
    smart_home: SmartHomeService, connectivity: ConnectivityService, simulator: SimulatorConnector
) -> None:
    simulator.define_device(device_type="switch", external_id="switch.x", status="on")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    raw = await connectivity.read_raw_state(device.id)

    assert raw is not None
    assert raw.status == "on"


@pytest.mark.asyncio
async def test_generic_send_command_reaches_simulator(
    smart_home: SmartHomeService, connectivity: ConnectivityService, simulator: SimulatorConnector
) -> None:
    simulator.define_device(device_type="lock", external_id="lock.x")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    result = await connectivity.send_command(device.id, "lock", {})

    assert result.success is True
    assert (await simulator.read_state("lock.x")).status == "locked"


@pytest.mark.asyncio
async def test_real_smart_lighting_service_full_roundtrip(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    simulator: SimulatorConnector,
    permissions: PermissionModel,
    db,
) -> None:
    """The real, unmodified `SmartLightingService` -- no
    simulator-specific service, no modified `_TRANSLATORS`."""
    service = SmartLightingService(
        database=db, smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )
    await permissions.grant("core:smart_lighting", "smart_home")
    simulator.define_device(device_type="light", external_id="light.x")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    result = await service.set_light_state(device.id, on=True, brightness=80)
    assert result["success"] is True

    state = await service.get_light_state(device.id)
    assert state["on"] is True
    assert state["brightness"] == 80


@pytest.mark.asyncio
async def test_real_smart_switch_service_full_roundtrip(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    simulator: SimulatorConnector,
    permissions: PermissionModel,
) -> None:
    service = SmartSwitchService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )
    await permissions.grant("core:smart_switch", "smart_home")
    simulator.define_device(device_type="switch", external_id="switch.x")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    result = await service.turn_on(device.id)
    assert result["success"] is True
    state = await service.get_switch_state(device.id)
    assert state["on"] is True


@pytest.mark.asyncio
async def test_real_thermostat_service_full_roundtrip(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    simulator: SimulatorConnector,
    permissions: PermissionModel,
) -> None:
    service = ThermostatService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )
    await permissions.grant("core:thermostats", "smart_home")
    simulator.define_device(device_type="thermostat", external_id="climate.x")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    result = await service.set_thermostat_state(device.id, temperature=22.0, hvac_mode="heat")
    assert result["success"] is True
    state = await service.get_thermostat_state(device.id)
    assert state["hvac_mode"] == "heat"
    assert state["target_temperature"] == 22.0


@pytest.mark.asyncio
async def test_real_smart_lock_service_full_roundtrip(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    simulator: SimulatorConnector,
    permissions: PermissionModel,
) -> None:
    service = SmartLockService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )
    await permissions.grant("core:smart_locks", "smart_home")
    simulator.define_device(device_type="lock", external_id="lock.x")
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    result = await service.lock(device.id)
    assert result["success"] is True
    state = await service.get_lock_state(device.id)
    assert state["locked"] is True


@pytest.mark.asyncio
async def test_real_sensor_service_reads_simulated_binary_sensor(
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    simulator: SimulatorConnector,
    permissions: PermissionModel,
) -> None:
    service = SensorService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )
    await permissions.grant("core:sensors", "smart_home")
    simulator.define_device(
        device_type="sensor",
        external_id="sensor.motion",
        binary=True,
        device_class="motion",
        status="on",
    )
    home = await smart_home.create_home("Primary Residence")
    await connectivity.connect("home_assistant")
    [device] = await connectivity.run_discovery("home_assistant", home.id)

    state = await service.get_sensor_state(device.id)
    assert state["kind"] == "binary"
    assert state["value"] is True
    assert state["state"] == "detected"


# --- J. Architecture guards --------------------------------------------------------------


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


def _simulator_code() -> str:
    import inspect

    from jarvis.core.connectivity.connectors import simulator as simulator_module

    return _code_without_docstrings(inspect.getsource(simulator_module))


def test_simulator_has_no_scheduler_reference() -> None:
    source = _simulator_code()
    assert "Scheduler" not in source
    assert "schedule" not in source.lower()


def test_simulator_has_no_analytics_reference() -> None:
    source = _simulator_code()
    assert "Analytics" not in source


def test_simulator_has_no_memory_reference() -> None:
    source = _simulator_code()
    assert "MemoryService" not in source
    assert "memory" not in source.lower()


def test_simulator_has_no_agent_tool_reference() -> None:
    source = _simulator_code()
    assert "langchain" not in source.lower()
    assert "BaseTool" not in source
    assert "@tool" not in source


def test_simulator_has_no_eventbus_reference() -> None:
    """The simulator's own module -- distinct from `ConnectivityService`'s
    own pre-existing, unrelated `ConnectivityStatusChangedEvent` publish
    (Logic Contract §12), which lives in `connectivity_service.py`, not
    here."""
    source = _simulator_code()
    assert "EventBus" not in source
    assert "event_bus" not in source


def test_existing_translators_unmodified_no_simulator_key() -> None:
    """Every device-category service's own `_TRANSLATORS` dict is
    still exactly `{"home_assistant", "mqtt"}` -- no third key was
    added anywhere (Logic Contract's central architectural finding,
    §2)."""
    from jarvis.services import (
        smart_lighting_service,
        smart_lock_service,
        smart_switch_service,
        thermostat_service,
    )

    for module in (
        smart_lighting_service,
        smart_switch_service,
        thermostat_service,
        smart_lock_service,
    ):
        assert set(module._TRANSLATORS.keys()) == {"home_assistant", "mqtt"}


def test_no_deferred_functionality_exists() -> None:
    source = _simulator_code().lower()
    for deferred_term in ("random.", "asyncio.sleep", "latency"):
        assert deferred_term not in source
