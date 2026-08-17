"""AlarmControlPanelService tests -- Milestone 12 Security & Safety
(alarm_control_panel Integration Slice).

Real (temp-file) SQLite ``SmartHomeService`` and a real
``PermissionModel`` throughout, matching
``test_m12_siren_service.py``'s own pattern -- only the connector
itself is faked (``FakeDeviceConnector``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.core.connectivity.registry import ConnectorFactoryRegistry
from jarvis.core.events.event_bus import EventBus
from jarvis.core.exceptions import ServiceError
from jarvis.core.interfaces.connectivity import DeviceState
from jarvis.core.plugins.permissions import PermissionModel
from jarvis.services.alarm_control_panel_service import (
    ALARM_CONTROL_PANEL_PRINCIPAL,
    SMART_HOME_SCOPE,
    AlarmControlPanelService,
)
from jarvis.services.connectivity_service import ConnectivityService
from jarvis.services.smart_home_service import SmartHomeService
from tests.fakes.fake_device_connector import FakeDeviceConnector

_ALL_VERIFIED_HA_STATES = (
    "disarmed",
    "armed_home",
    "armed_away",
    "armed_night",
    "armed_vacation",
    "armed_custom_bypass",
    "pending",
    "arming",
    "disarming",
    "triggered",
)


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
def service(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> AlarmControlPanelService:
    return AlarmControlPanelService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(ALARM_CONTROL_PANEL_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_panel(
    smart_home: SmartHomeService,
    *,
    connector_type: str = "home_assistant",
    domain_key: str = "domain",
    home_id: str | None = None,
):
    if home_id is None:
        home = await smart_home.create_home("Primary Residence")
        home_id = home.id
    else:
        home = None
    device = await smart_home.register_discovered_device(
        home_id,
        "Front Panel",
        device_type="other",
        external_id="alarm_control_panel.front",
        metadata={"connector_type": connector_type, domain_key: "alarm_control_panel"},
    )
    return home, device


# --- Identity -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(ALARM_CONTROL_PANEL_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_domain_key_identifies_a_panel(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home, domain_key="domain")
    rows = await service.list_alarm_control_panels()
    assert [r["id"] for r in rows] == [device.id]


@pytest.mark.asyncio
async def test_component_key_identifies_a_panel(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    """MQTT Discovery-sourced devices carry `component` rather than
    `domain` -- see Logic Contract §4's fallback order."""
    _, device = await _home_and_panel(smart_home, connector_type="mqtt", domain_key="component")
    rows = await service.list_alarm_control_panels()
    assert [r["id"] for r in rows] == [device.id]


@pytest.mark.asyncio
async def test_domain_takes_precedence_over_component(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Ambiguous Entity",
        device_type="other",
        external_id="other.ambiguous",
        metadata={
            "connector_type": "home_assistant",
            "domain": "alarm_control_panel",
            "component": "switch",
        },
    )
    state = await service.get_alarm_control_panel_state(device.id)
    assert state["id"] == device.id


@pytest.mark.asyncio
async def test_wrong_domain_is_rejected(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Motion Sensor",
        device_type="other",
        external_id="binary_sensor.motion",
        metadata={"connector_type": "home_assistant", "domain": "binary_sensor"},
    )
    with pytest.raises(ServiceError, match="not an alarm control panel"):
        await service.get_alarm_control_panel_state(device.id)


@pytest.mark.asyncio
async def test_missing_metadata_is_rejected(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "No Metadata", device_type="other"
    )
    with pytest.raises(ServiceError, match="not an alarm control panel"):
        await service.get_alarm_control_panel_state(device.id)


@pytest.mark.asyncio
async def test_wrong_device_type_is_rejected_even_with_matching_domain(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Odd Switch",
        device_type="switch",
        external_id="switch.odd",
        metadata={"connector_type": "home_assistant", "domain": "alarm_control_panel"},
    )
    with pytest.raises(ServiceError, match="not an alarm control panel"):
        await service.get_alarm_control_panel_state(device.id)


@pytest.mark.asyncio
async def test_siren_domain_is_rejected_not_confused_with_alarm_control_panel(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    """A sibling `device_type="other"` category (siren) must never
    false-match as an alarm control panel."""
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Yard Siren",
        device_type="other",
        external_id="siren.front_yard",
        metadata={"connector_type": "home_assistant", "domain": "siren"},
    )
    with pytest.raises(ServiceError, match="not an alarm control panel"):
        await service.get_alarm_control_panel_state(device.id)


@pytest.mark.asyncio
async def test_list_excludes_non_alarm_other_devices(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    home = await smart_home.create_home("Primary Residence")
    await smart_home.register_discovered_device(
        home.id,
        "Front Yard Siren",
        device_type="other",
        external_id="siren.front_yard",
        metadata={"connector_type": "home_assistant", "domain": "siren"},
    )
    _, panel = await _home_and_panel(smart_home, home_id=home.id)

    rows = await service.list_alarm_control_panels()

    assert [r["id"] for r in rows] == [panel.id]


# --- Permission enforcement ----------------------------------------------------


@pytest.mark.asyncio
async def test_arm_home_denied_by_default(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.arm_home(device.id)


@pytest.mark.asyncio
async def test_arm_away_denied_by_default(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.arm_away(device.id)


@pytest.mark.asyncio
async def test_disarm_denied_by_default(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.disarm(device.id)


@pytest.mark.asyncio
async def test_read_only_operations_do_not_require_permission(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)
    rows = await service.list_alarm_control_panels()
    assert len(rows) == 1
    state = await service.get_alarm_control_panel_state(device.id)
    assert state["id"] == device.id


# --- Validation ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_arm_home_rejects_device_with_no_connector(
    service: AlarmControlPanelService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id, "Orphan Panel", device_type="other", metadata={"domain": "alarm_control_panel"}
    )
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.arm_home(device.id)


@pytest.mark.asyncio
async def test_arm_home_rejects_unsupported_connector_type(
    service: AlarmControlPanelService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.arm_home(device.id)


@pytest.mark.asyncio
async def test_arm_home_unknown_device_raises(
    service: AlarmControlPanelService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    with pytest.raises(ServiceError):
        await service.arm_home("no-such-device")


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_arm_home_translation(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home)

    result = await service.arm_home(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("alarm_control_panel.front", "alarm_arm_home", {})]


@pytest.mark.asyncio
async def test_ha_arm_away_translation(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home)

    result = await service.arm_away(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("alarm_control_panel.front", "alarm_arm_away", {})]


@pytest.mark.asyncio
async def test_ha_disarm_translation(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home)

    result = await service.disarm(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("alarm_control_panel.front", "alarm_disarm", {})]


@pytest.mark.asyncio
async def test_no_command_ever_carries_a_code_field(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Every payload sent for every action is an empty dict -- no
    `code`/`pin` key ever appears (Logic Contract §8)."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home)

    await service.arm_home(device.id)
    await service.arm_away(device.id)
    await service.disarm(device.id)

    for _external_id, _command, payload in fake_connector.sent_commands:
        assert payload == {}
        assert "code" not in payload
        assert "pin" not in payload


# --- MQTT translation -------------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_arm_home_arm_away_disarm_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = AlarmControlPanelService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home, connector_type="mqtt", domain_key="component")

    await mqtt_service.arm_home(device.id)
    await mqtt_service.arm_away(device.id)
    await mqtt_service.disarm(device.id)

    assert mqtt_connector.sent_commands == [
        ("alarm_control_panel.front", "arm_home", {}),
        ("alarm_control_panel.front", "arm_away", {}),
        ("alarm_control_panel.front", "disarm", {}),
    ]


# --- Reads: live state merge ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("ha_state", _ALL_VERIFIED_HA_STATES)
async def test_get_state_reports_each_verified_ha_state(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
    ha_state: str,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_panel(smart_home)
    fake_connector.states["alarm_control_panel.front"] = DeviceState(
        external_id="alarm_control_panel.front", status=ha_state, attributes={}
    )

    state = await service.get_alarm_control_panel_state(device.id)

    assert state["state"] == ha_state
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_state_unrecognized_status_reports_none(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """Never fabricates a state the connector layer does not itself
    represent -- see Logic Contract §5/§7."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_panel(smart_home)
    fake_connector.states["alarm_control_panel.front"] = DeviceState(
        external_id="alarm_control_panel.front", status="some_unknown_status", attributes={}
    )

    state = await service.get_alarm_control_panel_state(device.id)

    assert state["state"] is None
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_state_falls_back_when_connector_unreachable(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)

    state = await service.get_alarm_control_panel_state(device.id)

    assert state["id"] == device.id
    assert state["state"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_connector_reported_offline_status_marks_unavailable(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_panel(smart_home)
    fake_connector.states["alarm_control_panel.front"] = DeviceState(
        external_id="alarm_control_panel.front", status="unavailable", attributes={}
    )

    state = await service.get_alarm_control_panel_state(device.id)

    assert state["available"] is False
    assert state["state"] is None


@pytest.mark.asyncio
async def test_list_does_not_make_a_live_connector_read(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_panel(smart_home)
    fake_connector.states["alarm_control_panel.front"] = DeviceState(
        external_id="alarm_control_panel.front", status="armed_home", attributes={}
    )

    rows = await service.list_alarm_control_panels()

    assert len(rows) == 1
    assert rows[0]["state"] is None  # DB-only -- see list_alarm_control_panels docstring.


# --- Security: no metadata_json leakage -------------------------------------------


@pytest.mark.asyncio
async def test_payload_never_includes_raw_metadata_json(
    service: AlarmControlPanelService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_panel(smart_home)
    state = await service.get_alarm_control_panel_state(device.id)
    assert "metadata" not in state
    assert "metadata_json" not in state
    assert set(state.keys()) == {
        "id",
        "home_id",
        "room_id",
        "name",
        "status",
        "manufacturer",
        "model",
        "external_id",
        "state",
        "available",
    }


# --- Failure honesty ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_command_reports_failure_not_success(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_panel(smart_home)

    result = await service.disarm(device.id)

    assert result["success"] is False
    assert result["detail"]


@pytest.mark.asyncio
async def test_arm_home_is_not_deduplicated_when_called_twice(
    service: AlarmControlPanelService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_panel(smart_home)

    await service.arm_home(device.id)
    await service.arm_home(device.id)

    assert fake_connector.sent_commands == [
        ("alarm_control_panel.front", "alarm_arm_home", {}),
        ("alarm_control_panel.front", "alarm_arm_home", {}),
    ]


# --- Cross-cutting invariants -------------------------------------------------------


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


def _service_code() -> str:
    import inspect

    from jarvis.services import alarm_control_panel_service

    return _code_without_docstrings(inspect.getsource(alarm_control_panel_service))


def test_no_alarm_history_panic_vacation_siren_or_boundary_violations() -> None:
    code = _service_code()
    for forbidden_term in (
        "trigger_panic_mode",
        "trigger_vacation_mode",
        "SirenService",
        "SecurityService",
        "EventBus",
        "Scheduler",
        "MemoryService",
        "SmartHomeMemoryService",
        "notification",
    ):
        assert forbidden_term not in code


def test_no_deferred_arm_modes_or_trigger_action_exist() -> None:
    """`arm_night`/`arm_vacation`/`arm_custom_bypass`/`trigger` must
    never appear as real code -- only in explanatory docstrings
    discussing why they are deferred (Logic Contract §21)."""
    code = _service_code()
    for deferred_term in (
        "arm_night",
        "arm_vacation",
        "arm_custom_bypass",
        "alarm_trigger",
        "ARM_NIGHT",
        "ARM_VACATION",
        "ARM_CUSTOM_BYPASS",
        "TRIGGER",
    ):
        assert deferred_term not in code


def test_no_code_or_pin_parameter_exists_anywhere_in_the_module() -> None:
    """Structural, not a redaction check -- no function/method
    signature in this module has ever defined a `code`/`pin` parameter
    (Logic Contract §8)."""
    import inspect

    from jarvis.services import alarm_control_panel_service

    for _name, obj in inspect.getmembers(alarm_control_panel_service):
        if inspect.isfunction(obj) or inspect.iscoroutinefunction(obj):
            params = set(inspect.signature(obj).parameters)
            assert "code" not in params
            assert "pin" not in params
    service_members = inspect.getmembers(
        alarm_control_panel_service.AlarmControlPanelService, predicate=inspect.isfunction
    )
    for _name, method in service_members:
        params = set(inspect.signature(method).parameters)
        assert "code" not in params
        assert "pin" not in params


def test_service_does_not_import_connectors_directly() -> None:
    import inspect

    from jarvis.services import alarm_control_panel_service

    import_lines = [
        line
        for line in inspect.getsource(alarm_control_panel_service).splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    joined = "\n".join(import_lines)
    assert "HomeAssistantConnector" not in joined
    assert "MqttConnector" not in joined
