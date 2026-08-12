"""SmartLockService tests -- Milestone 12 Smart Locks.

Real (temp-file) SQLite ``SmartHomeService`` and a real ``PermissionModel``
throughout, matching ``test_m12_smart_lighting_service.py``'s own
pattern -- only the connector itself is faked (``FakeDeviceConnector``).
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
from jarvis.services.smart_home_service import SmartHomeService
from jarvis.services.smart_lock_service import (
    SMART_HOME_SCOPE,
    SMART_LOCK_PRINCIPAL,
    SmartLockService,
)
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
def service(
    smart_home: SmartHomeService, connectivity: ConnectivityService, permissions: PermissionModel
) -> SmartLockService:
    return SmartLockService(
        smart_home=smart_home, connectivity=connectivity, permissions=permissions
    )


async def _grant(permissions: PermissionModel) -> None:
    await permissions.grant(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE)


async def _home_and_lock(smart_home: SmartHomeService, connector_type: str = "home_assistant"):
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(
        home.id,
        "Front Door Lock",
        device_type="lock",
        external_id="lock.front_door",
        metadata={"connector_type": connector_type},
    )
    return home, device


# --- Permission enforcement --------------------------------------------------


@pytest.mark.asyncio
async def test_lock_denied_by_default(
    service: SmartLockService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_lock(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.lock(device.id)


@pytest.mark.asyncio
async def test_unlock_denied_by_default(
    service: SmartLockService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_lock(smart_home)
    with pytest.raises(ServiceError, match="permission"):
        await service.unlock(device.id)


@pytest.mark.asyncio
async def test_permission_declared_pending_at_construction(permissions: PermissionModel) -> None:
    assert permissions.state(SMART_LOCK_PRINCIPAL, SMART_HOME_SCOPE).value == "pending"


@pytest.mark.asyncio
async def test_read_only_operations_do_not_require_permission(
    service: SmartLockService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_lock(smart_home)
    locks = await service.list_locks()
    assert len(locks) == 1
    state = await service.get_lock_state(device.id)
    assert state["id"] == device.id


# --- Validation ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_lock_rejects_non_lock_device(
    service: SmartLockService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    switch = await smart_home.register_discovered_device(
        home.id, "Hallway Switch", device_type="switch", external_id="switch.hallway"
    )
    with pytest.raises(ServiceError, match="not a lock"):
        await service.lock(switch.id)


@pytest.mark.asyncio
async def test_lock_rejects_device_with_no_connector(
    service: SmartLockService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    home = await smart_home.create_home("Primary Residence")
    device = await smart_home.register_discovered_device(home.id, "Orphan Lock", device_type="lock")
    with pytest.raises(ServiceError, match="no recorded connector"):
        await service.lock(device.id)


@pytest.mark.asyncio
async def test_lock_rejects_unsupported_connector_type(
    service: SmartLockService, smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    await _grant(permissions)
    _, device = await _home_and_lock(smart_home, connector_type="zigbee")
    with pytest.raises(ServiceError, match="no command translation"):
        await service.lock(device.id)


# --- Home Assistant translation ------------------------------------------------


@pytest.mark.asyncio
async def test_ha_lock_translation(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_lock(smart_home)

    result = await service.lock(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("lock.front_door", "lock", {})]


@pytest.mark.asyncio
async def test_ha_unlock_translation(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_lock(smart_home)

    result = await service.unlock(device.id)

    assert result["success"] is True
    assert fake_connector.sent_commands == [("lock.front_door", "unlock", {})]


# --- MQTT translation -----------------------------------------------------------


@pytest.mark.asyncio
async def test_mqtt_lock_and_unlock_translation(
    smart_home: SmartHomeService, permissions: PermissionModel
) -> None:
    mqtt_connector = FakeDeviceConnector()
    mqtt_connector.connector_type = "mqtt"
    registry = ConnectorFactoryRegistry()
    registry.register("mqtt", lambda config: mqtt_connector)
    mqtt_connectivity = ConnectivityService(registry=registry, smart_home=smart_home)
    mqtt_service = SmartLockService(
        smart_home=smart_home, connectivity=mqtt_connectivity, permissions=permissions
    )
    await mqtt_connectivity.connect("mqtt")
    await _grant(permissions)
    _, device = await _home_and_lock(smart_home, connector_type="mqtt")

    await mqtt_service.lock(device.id)
    await mqtt_service.unlock(device.id)

    assert mqtt_connector.sent_commands == [
        ("lock.front_door", "lock", {}),
        ("lock.front_door", "unlock", {}),
    ]


# --- Reads: live state merge ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_lock_state_reports_locked_true(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_lock(smart_home)
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )

    state = await service.get_lock_state(device.id)

    assert state["locked"] is True
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_lock_state_reports_locked_false(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    _, device = await _home_and_lock(smart_home)
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="unlocked", attributes={}
    )

    state = await service.get_lock_state(device.id)

    assert state["locked"] is False


@pytest.mark.asyncio
async def test_get_lock_state_reports_unknown_for_unmodeled_status(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    """`jammed`/`locking`/`unlocking` are not represented by either
    connector's own state normalization -- see Logic Contract §4."""
    await connectivity.connect("home_assistant")
    _, device = await _home_and_lock(smart_home)
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="jammed", attributes={}
    )

    state = await service.get_lock_state(device.id)

    assert state["locked"] is None
    assert state["available"] is True


@pytest.mark.asyncio
async def test_get_lock_state_falls_back_when_connector_unreachable(
    service: SmartLockService, smart_home: SmartHomeService
) -> None:
    _, device = await _home_and_lock(smart_home)

    state = await service.get_lock_state(device.id)

    assert state["id"] == device.id
    assert state["locked"] is None
    assert state["available"] is False


@pytest.mark.asyncio
async def test_list_locks_does_not_make_a_live_connector_read(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _home_and_lock(smart_home)
    fake_connector.states["lock.front_door"] = DeviceState(
        external_id="lock.front_door", status="locked", attributes={}
    )

    rows = await service.list_locks()

    assert len(rows) == 1
    assert rows[0]["locked"] is None  # DB-only -- see SmartLockService.list_locks docstring.


# --- Idempotency + failure honesty ----------------------------------------------


@pytest.mark.asyncio
async def test_lock_is_not_deduplicated_when_called_twice(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    """No command-diffing/idempotency short-circuit exists anywhere in
    the Connectivity Layer -- see Logic Contract §17."""
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    _, device = await _home_and_lock(smart_home)

    await service.lock(device.id)
    await service.lock(device.id)

    assert fake_connector.sent_commands == [
        ("lock.front_door", "lock", {}),
        ("lock.front_door", "lock", {}),
    ]


@pytest.mark.asyncio
async def test_failed_command_reports_failure_not_success(
    service: SmartLockService,
    smart_home: SmartHomeService,
    connectivity: ConnectivityService,
    permissions: PermissionModel,
    fake_connector: FakeDeviceConnector,
) -> None:
    await connectivity.connect("home_assistant")
    await _grant(permissions)
    fake_connector.next_command_succeeds = False
    _, device = await _home_and_lock(smart_home)

    result = await service.unlock(device.id)

    assert result["success"] is False
    assert result["detail"]


# --- Cross-cutting invariant ------------------------------------------------------


def test_domain_layer_has_no_vendor_wire_format_leakage() -> None:
    import inspect

    from jarvis.domain.smart_home import models as domain_models
    from jarvis.services import smart_home_service

    source = inspect.getsource(domain_models) + inspect.getsource(smart_home_service)
    for leaked_term in ("lock.lock", "lock.unlock", "jammed"):
        assert leaked_term not in source
